#!/bin/sh
set -eu

usage() {
  echo "Usage: process-video.sh <youtube-url>" >&2
  exit 2
}

[ "$#" -eq 1 ] || usage

video_url=$1

# Deliberately accepts only a single video ID. Add playlists and other YouTube
# URL forms only after they have their own validation and resource limits.
case "$video_url" in
  https://www.youtube.com/watch?v=???????????|https://youtube.com/watch?v=???????????|https://youtu.be/???????????) ;;
  *)
    echo "Only a basic youtube.com/watch or youtu.be URL with an 11-character video ID is accepted." >&2
    exit 2
    ;;
esac

case "$video_url" in
  *[!A-Za-z0-9_:/?=.-]*)
    echo "The URL contains unsupported characters." >&2
    exit 2
    ;;
esac

job_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
job_dir="/data/jobs/$job_id"
mkdir -p "$job_dir"

yt-dlp \
  --no-playlist \
  --js-runtimes node \
  --write-info-json \
  --merge-output-format mp4 \
  --output "$job_dir/video.%(ext)s" \
  "$video_url" >&2

video_path=$(find "$job_dir" -maxdepth 1 -type f ! -name '*.json' | head -n 1)
[ -n "$video_path" ] || {
  echo "yt-dlp completed without producing a video file." >&2
  exit 1
}

node /opt/scripts/media-result.mjs \
  "$job_id" \
  "$job_dir" \
  "$video_path" \
  "$job_dir/video.info.json"
