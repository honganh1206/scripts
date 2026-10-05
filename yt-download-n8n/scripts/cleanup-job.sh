#!/bin/sh
set -eu

[ "$#" -eq 1 ] || {
  echo "Usage: cleanup-job.sh <job-directory>" >&2
  exit 2
}

job_dir=$1
job_name=${job_dir#/data/jobs/}

if [ "$job_dir" != "/data/jobs/$job_name" ]; then
  echo "Refusing to remove an unexpected path: $job_dir" >&2
  exit 2
fi

case "$job_name" in
  ""|*[!A-Za-z0-9_-]*)
    echo "Refusing to remove an unexpected path: $job_dir" >&2
    exit 2
    ;;
esac

[ -d "$job_dir" ] || {
  echo "The temporary job directory no longer exists: $job_dir" >&2
  exit 1
}

rm -rf "$job_dir"
printf '{"cleaned":true,"jobDir":"%s"}\n' "$job_dir"
