import { readFile, writeFile } from 'node:fs/promises';

const [audioPath, transcriptPath, jobId, jobDir, videoPath] = process.argv.slice(2);

if (!audioPath || !transcriptPath || !jobId || !jobDir || !videoPath) {
  console.error('The transcription helper did not receive all required paths.');
  process.exit(2);
}

const apiKey = process.env.OPENAI_API_KEY;
if (!apiKey) {
  console.error('OPENAI_API_KEY must be set.');
  process.exit(2);
}

const baseUrl = (process.env.OPENAI_BASE_URL || 'https://api.openai.com/v1').replace(/\/$/, '');
const model = process.env.OPENAI_TRANSCRIPTION_MODEL || 'whisper-1';
const audio = await readFile(audioPath);
const form = new FormData();
form.append('model', model);
form.append('file', new Blob([audio], { type: 'audio/mpeg' }), 'audio.mp3');

const response = await fetch(`${baseUrl}/audio/transcriptions`, {
  method: 'POST',
  headers: { Authorization: `Bearer ${apiKey}` },
  body: form,
});
const body = await response.text();

if (!response.ok) {
  console.error(`OpenAI transcription failed with HTTP ${response.status}:`);
  console.error(body);
  process.exit(1);
}

let transcript;
try {
  transcript = JSON.parse(body);
} catch {
  console.error('OpenAI returned a successful response that was not valid JSON.');
  process.exit(1);
}

await writeFile(transcriptPath, `${JSON.stringify(transcript, null, 2)}\n`);

console.log(JSON.stringify({
  jobId,
  jobDir,
  videoPath,
  audioPath,
  transcriptPath,
  provider: 'openai',
  model,
  text: transcript.text || '',
}));
