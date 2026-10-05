#!/usr/bin/env python3
"""Download a YouTube video and its transcript into a numbered folder."""

import argparse
import os
import re
import sys
from pathlib import Path

import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter


def extract_video_id(url: str) -> str:
    """Extract the video ID from a YouTube URL."""
    patterns = [
        r'(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'(?:embed/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError(f"Could not extract video ID from: {url}")


def get_downloads_dir() -> Path:
    """Return the user's Downloads directory."""
    return Path.home() / "Downloads"


def title_to_snake_case(title: str) -> str:
    """Convert a video title to snake_case folder name."""
    # Remove non-alphanumeric chars (keep spaces)
    clean = re.sub(r'[^\w\s-]', '', title)
    # Replace whitespace/hyphens with underscores, collapse multiples, strip, lowercase
    return re.sub(r'[\s\-]+', '_', clean).strip('_').lower()


def extract_title(url: str) -> str:
    """Extract the video title without downloading."""
    with yt_dlp.YoutubeDL({'quiet': True, 'skip_download': True}) as ydl:
        info = ydl.extract_info(url, download=False)
        return info.get('title', 'video')


def make_output_folder(base_dir: Path, title: str) -> Path:
    """Create a snake_case folder from the video title, appending _N if it exists."""
    folder_name = title_to_snake_case(title)
    folder = base_dir / folder_name
    if folder.exists():
        n = 2
        while (base_dir / f"{folder_name}_{n}").exists():
            n += 1
        folder = base_dir / f"{folder_name}_{n}"
    folder.mkdir(parents=True)
    return folder


def download_video(url: str, output_dir: Path) -> str:
    """Download the video using yt-dlp. Returns the final filename."""
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': str(output_dir / '%(title)s [%(id)s].%(ext)s'),
        'merge_output_format': 'mp4',
        'quiet': False,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return info.get('title', 'video')


def fetch_transcript(video_id: str, output_dir: Path) -> bool:
    """Fetch the transcript and save it as a text file. Returns True on success."""
    try:
        ytt_api = YouTubeTranscriptApi()
        transcript = ytt_api.fetch(video_id)

        formatter = TextFormatter()
        text = formatter.format_transcript(transcript)

        transcript_path = output_dir / "transcript.txt"
        transcript_path.write_text(text, encoding="utf-8")
        print(f"\n✅ Transcript saved to: {transcript_path}")
        return True
    except Exception as e:
        print(f"\n⚠️  Could not fetch transcript: {e}", file=sys.stderr)
        # Fallback: try yt-dlp auto-subs
        print("   Trying yt-dlp auto-generated subtitles as fallback...")
        return fetch_transcript_ytdlp(video_id, output_dir)


def fetch_transcript_ytdlp(video_id: str, output_dir: Path) -> bool:
    """Fallback: grab auto-generated subs via yt-dlp."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {
        'writeautomaticsub': True,
        'subtitleslangs': ['en'],
        'subtitlesformat': 'vtt',
        'skip_download': True,
        'outtmpl': str(output_dir / 'subs'),
        'quiet': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # Find the downloaded vtt file and extract plain text
        for f in output_dir.iterdir():
            if f.suffix == '.vtt':
                lines = f.read_text(encoding='utf-8').splitlines()
                text_lines = []
                for line in lines:
                    line = line.strip()
                    if not line or line.startswith('WEBVTT') or line.startswith('Kind:') \
                            or line.startswith('Language:') or '-->' in line or line.isdigit():
                        continue
                    # Remove VTT tags
                    clean = re.sub(r'<[^>]+>', '', line)
                    if clean and clean not in text_lines[-1:]:
                        text_lines.append(clean)

                transcript_path = output_dir / "transcript.txt"
                transcript_path.write_text('\n'.join(text_lines), encoding='utf-8')
                f.unlink()  # remove the vtt file
                print(f"   ✅ Transcript (auto-generated) saved to: {transcript_path}")
                return True

        print("   ❌ No subtitles found for this video.", file=sys.stderr)
        return False
    except Exception as e:
        print(f"   ❌ Fallback also failed: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="Download a YouTube video + transcript")
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument(
        "-d", "--directory",
        default=None,
        help="Base directory for output folders (default: ~/Downloads)",
    )
    args = parser.parse_args()

    video_id = extract_video_id(args.url)
    base_dir = Path(args.directory) if args.directory else get_downloads_dir()

    print("🔍 Fetching video info...")
    title = extract_title(args.url)
    folder = make_output_folder(base_dir, title)
    print(f"📂 Output folder: {folder}\n")

    print("⬇️  Downloading video...")
    title = download_video(args.url, folder)
    print(f"\n✅ Video downloaded: {title}")

    print("\n📝 Fetching transcript...")
    fetch_transcript(video_id, folder)

    print(f"\n🎉 Done! All files are in: {folder}")


if __name__ == "__main__":
    main()
