ARG N8N_VERSION=2.39.7

FROM alpine:3.22 AS yt-dlp

RUN wget -q -O /yt-dlp \
    "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_musllinux" \
    && chmod 0755 /yt-dlp

FROM mwader/static-ffmpeg:7.1 AS ffmpeg

FROM n8nio/n8n:${N8N_VERSION}

USER root

COPY --from=yt-dlp /yt-dlp /usr/local/bin/yt-dlp
COPY --from=ffmpeg /ffmpeg /usr/local/bin/ffmpeg
COPY --chown=node:node scripts/process-video.sh /opt/scripts/process-video.sh
COPY --chown=node:node scripts/transcribe-video.sh /opt/scripts/transcribe-video.sh
COPY --chown=node:node scripts/prepare-audio-upload.sh /opt/scripts/prepare-audio-upload.sh
COPY --chown=node:node scripts/cleanup-job.sh /opt/scripts/cleanup-job.sh
COPY --chown=node:node scripts/media-result.mjs /opt/scripts/media-result.mjs
COPY --chown=node:node scripts/transcribe.mjs /opt/scripts/transcribe.mjs
RUN chmod 0755 \
    /opt/scripts/process-video.sh \
    /opt/scripts/transcribe-video.sh \
    /opt/scripts/prepare-audio-upload.sh \
    /opt/scripts/cleanup-job.sh

USER node
