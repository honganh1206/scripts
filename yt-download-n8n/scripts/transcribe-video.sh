#!/bin/sh
set -eu

[ "$#" -eq 3 ] || {
  echo "Usage: transcribe-video.sh <job-id> <job-directory> <video-path>" >&2
  exit 2
}

job_id=$1
job_dir=$2
video_path=$3

case "$job_id:$job_dir:$video_path" in
  *[!A-Za-z0-9_./:-]*)
    echo "The generated job paths contain unsupported characters." >&2
    exit 2
    ;;
esac

case "$job_dir:$video_path" in
  /data/jobs/"$job_id":/data/jobs/"$job_id"/*) ;;
  *)
    echo "The generated job paths do not belong to the expected job directory." >&2
    exit 2
    ;;
esac

: "${OPENAI_API_KEY:?OPENAI_API_KEY must be set}"
[ -f "$video_path" ] || {
  echo "The downloaded video file does not exist." >&2
  exit 1
}

audio_path="$job_dir/audio.mp3"
ffmpeg -hide_banner -loglevel error -y \
  -i "$video_path" \
  -vn -ac 1 -ar 16000 -b:a 64k \
  "$audio_path"

transcript_path="$job_dir/transcript.json"
node /opt/scripts/transcribe.mjs \
  "$audio_path" \
  "$transcript_path" \
  "$job_id" \
  "$job_dir" \
  "$video_path"
