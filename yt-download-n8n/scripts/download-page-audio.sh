#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "Usage: bash $0 <page-url> <output-directory> [rclone-destination]" >&2
  echo "Example: bash $0 https://example.com/test/ data/test-01 gdrive:English/A2/Test-01" >&2
  exit 2
fi

page_url=$1
output_dir=$2
destination=${3:-}

command -v curl >/dev/null
command -v python3 >/dev/null
if [[ -n "$destination" ]] && ! command -v rclone >/dev/null; then
  echo "Drive upload requires rclone and a configured Google Drive remote." >&2
  exit 2
fi

temp_dir=$(mktemp -d)
trap 'rm -rf "$temp_dir"' EXIT

# Use the final URL as the base for relative audio links after redirects.
base_url=$(curl --fail --silent --show-error --location \
  --connect-timeout 15 --max-time 120 --retry 2 \
  --output "$temp_dir/page.html" --write-out '%{url_effective}' "$page_url")

python3 - "$temp_dir/page.html" "$base_url" > "$temp_dir/audio.tsv" <<'PY'
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit


class AudioParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_audio = False
        self.urls = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'audio':
            self.in_audio = True
        if tag == 'audio' or (tag == 'source' and self.in_audio):
            if attrs.get('src'):
                url = urljoin(sys.argv[2], attrs['src'])
                if urlsplit(url).scheme in ('http', 'https') and url not in self.urls:
                    self.urls.append(url)

    def handle_endtag(self, tag):
        if tag == 'audio':
            self.in_audio = False


parser = AudioParser()
parser.feed(Path(sys.argv[1]).read_text(encoding='utf-8', errors='replace'))
if not parser.urls:
    sys.exit('No audio URLs found in the page HTML. JavaScript-only players are not supported.')
for index, url in enumerate(parser.urls, 1):
    if any(char in url for char in '\r\n\t'):
        sys.exit('An audio URL contains unsupported control characters.')
    basename = unquote(urlsplit(url).path.rsplit('/', 1)[-1])
    basename = re.sub(r'[^A-Za-z0-9._-]', '_', basename) or 'audio'
    # Numbering prevents collisions when different URLs share a filename.
    print(f'{index:02d}-{basename}\t{url}')
PY

mkdir -p "$output_dir"
while IFS=$'\t' read -r filename audio_url; do
  echo "Downloading $filename"
  curl --fail --silent --show-error --location \
    --connect-timeout 15 --max-time 600 --retry 2 \
    --referer "$base_url" --output "$temp_dir/audio.part" "$audio_url"
  mv "$temp_dir/audio.part" "$output_dir/$filename"
done < "$temp_dir/audio.tsv"

echo "Audio saved to $output_dir"
if [[ -n "$destination" ]]; then
  # Upload only this page's files, not unrelated files in the output directory.
  while IFS=$'\t' read -r filename audio_url; do
    rclone copyto "$output_dir/$filename" "${destination%/}/$filename"
  done < "$temp_dir/audio.tsv"
  echo "Audio uploaded to $destination (local copies kept)."
fi
