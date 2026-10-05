import { readFile } from 'node:fs/promises';
import { extname } from 'node:path';

const [jobId, jobDir, videoPath, metadataPath] = process.argv.slice(2);

if (!jobId || !jobDir || !videoPath || !metadataPath) {
  console.error('The media helper did not receive all required paths.');
  process.exit(2);
}

const metadata = JSON.parse(await readFile(metadataPath, 'utf8'));
const videoId = metadata.id || 'unknown-video';
const title = metadata.title || videoId;
const safeTitle = title
  .replace(/[\\/\u0000-\u001f\u007f]/g, ' - ')
  .replace(/\s+/g, ' ')
  .trim()
  .slice(0, 180) || videoId;
const extension = extname(videoPath) || '.mp4';

console.log(JSON.stringify({
  jobId,
  jobDir,
  videoPath,
  metadataPath,
  videoId,
  title,
  channel: metadata.channel || metadata.uploader || '',
  uploadDate: metadata.upload_date || '',
  sourceUrl: metadata.webpage_url || metadata.original_url || '',
  folderName: safeTitle,
  videoFileName: `${safeTitle}${extension}`,
}));
