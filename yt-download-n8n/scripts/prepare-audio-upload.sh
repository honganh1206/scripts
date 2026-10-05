#!/bin/sh
set -eu

[ "$#" -eq 2 ] || {
  echo "Usage: prepare-audio-upload.sh <job-id> <staged-path>" >&2
  exit 2
}

job_id=$1
staged_path=$2
job_dir="/data/jobs/$job_id"
expected_staged_path="/data/jobs/$job_id.source"

case "$job_id" in
  upload-[A-Za-z0-9_-]*) ;;
  *)
    echo "The upload job ID is invalid." >&2
    exit 2
    ;;
esac

if [ "$staged_path" != "$expected_staged_path" ]; then
  echo "The staged upload path is invalid." >&2
  exit 2
fi

[ -f "$staged_path" ] || {
  echo "The staged audio upload does not exist." >&2
  exit 1
}

mkdir "$job_dir"
source_path="$job_dir/source"
mv "$staged_path" "$source_path"

printf '{"jobId":"%s","jobDir":"%s","sourcePath":"%s"}\n' \
  "$job_id" \
  "$job_dir" \
  "$source_path"
