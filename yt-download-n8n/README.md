# YouTube download, Google Drive upload, and transcription workflow

This project runs a local n8n instance with `yt-dlp` and `ffmpeg`. Its first
workflow downloads one permitted YouTube video, uploads it to Google Drive,
transcribes it with OpenAI, creates a Google Doc containing the transcript, and
then deletes the temporary local files. A second workflow accepts an audio file
uploaded from the local browser and produces the same Drive and Docs output.

## Start n8n

1. Create the local environment file:

   ```sh
   cp .env.example .env
   ```

2. Add your OpenAI API key to `.env`.
3. Build and start n8n:

   ```sh
   docker compose up --build -d
   ```

4. Open <http://localhost:5678> and complete n8n's local owner setup.
5. Import `workflows/youtube-download.json` through **Import from File**.
6. Configure Google OAuth as described below.
7. Replace the placeholder in **Set inputs** with a video you are allowed to
   download, then run the workflow manually.

The final node returns links to the Drive folder, uploaded video, and transcript
document.

## Transcribe a local audio file

1. Import `workflows/local-audio-upload.json` through **Import from File**.
2. Select the Google OAuth credential in **Create Drive folder**, **Upload audio
   to Drive**, and **Create transcript Google Doc**.
3. Select **Execute Workflow** and open the test form from **Upload audio**.
4. Choose one local audio file. Keep `root` as the parent folder or enter a
   Google Drive folder ID, then select **Upload and transcribe**.

The form accepts MP3, MP4, MPEG, MPGA, M4A, WAV, WebM, OGG, FLAC, and AAC files.
It requires an authenticated n8n user and waits for transcription to finish
before displaying success. To use its production form URL, publish the workflow.

Local uploads are limited to 500 MiB by the workflow. The Docker configuration
allows form payloads up to 512 MiB; lower `N8N_PAYLOAD_SIZE_MAX` and
`N8N_FORMDATA_FILE_SIZE_MAX` if you do not need large WAV or FLAC uploads.

## Configure Google Drive

1. Create or select a project in the Google Cloud Console.
2. Enable both the **Google Drive API** and **Google Docs API**.
3. Configure the OAuth consent screen. If the app is in testing mode, add your
   Google account as a test user.
4. Create an OAuth client with application type **Web application**.
5. In n8n, open **Create Drive folder**, create a new Google Drive OAuth2
   credential, and copy the OAuth Redirect URL shown by n8n.
6. Add that URL to the Google OAuth client's **Authorized redirect URIs**.
7. Enter the Google client ID and client secret in n8n, then sign in to Google.
8. Select the same credential in **Create Drive folder**, the applicable
   **Upload video** or **Upload audio to Drive** node, and **Create transcript
   Google Doc**.

The YouTube workflow creates its video folders under:

<https://drive.google.com/drive/u/0/folders/19nePboHKnCJoJdHVoKUADoCpJyO0uRN1>

The `driveParentFolderId` form value controls where the local-audio workflow
creates its audio folder:

- Keep `root` to use the root of My Drive.
- For another folder, open that folder in Google Drive and copy the value after
  `/folders/` from its URL.

The workflows create these layouts:

```text
Configured local-audio parent folder/
└── Audio filename without extension/
    ├── Original audio file
    └── Audio filename without extension (Google Doc)

Configured YouTube parent folder/
└── Video title/
    ├── Video title.mp4
    └── Video title (Google Doc)
```

The media file is uploaded before transcription starts. Temporary files live
under `data/jobs/<job-id>/` only while the workflow runs. They are removed after
both the media file and Google Doc have been created. A failed execution
deliberately keeps its temporary files for diagnosis and retry.

## Current limits

- Only basic `youtube.com/watch?v=...` and `youtu.be/...` URLs are accepted.
- Playlists, URLs with additional query parameters, audio chunking, and retries
  are intentionally deferred.
- Re-running the same video creates another Drive folder; duplicate detection
  is intentionally deferred.
- The OpenAI upload limit still applies. Audio is converted to mono 16 kHz at
  64 kbit/s to keep uploads small. A 30-minute recording is approximately
  14.4 MB after conversion and fits in one transcription request.
- The Execute Command node is enabled because this instance binds only to
  `127.0.0.1`. Do not expose it publicly without authentication and stronger
  isolation.

Use these workflows only for media you own or have permission to process.

## Stop n8n

```sh
docker compose down
```

To also delete n8n's local database and credentials, run
`docker compose down --volumes`. This does not delete files under `data/`.
