import fs from "node:fs/promises";
import path from "node:path";
import { pipeline } from "node:stream/promises";
import { Readable } from "node:stream";
import ffmpeg from "fluent-ffmpeg";
const MAX_DOWNLOAD_BYTES = 250 * 1024 * 1024;
async function downloadHttps(inputUrl, dest) {
  const parsed = new URL(inputUrl);
  if (parsed.protocol !== "https:" || parsed.username || parsed.password) throw new Error("Only credential-free HTTPS media URLs are accepted.");
  const response = await fetch(parsed, { signal: AbortSignal.timeout(30000), redirect: "error" });
  if (!response.ok || !response.body) throw new Error(`Media download failed with HTTP ${response.status}.`);
  const length = Number(response.headers.get("content-length") || 0);
  if (length > MAX_DOWNLOAD_BYTES) throw new Error("Media file exceeds the 250 MB limit.");
  let bytes = 0;
  const limiter = new TransformStream({ transform(chunk, controller) { bytes += chunk.byteLength; if (bytes > MAX_DOWNLOAD_BYTES) throw new Error("Media file exceeds the 250 MB limit."); controller.enqueue(chunk); } });
  const handle = await fs.open(dest, "w");
  try { await pipeline(Readable.fromWeb(response.body.pipeThrough(limiter)), handle.createWriteStream()); } finally { await handle.close().catch(() => {}); }
}
export async function editVideo(props, outputPath, workDir) {
  const normalized = [];
  for (let i = 0; i < props.clips.length; i++) {
    const clip = props.clips[i], file = path.join(workDir, `clip-${i}.mp4`), target = path.join(workDir, `normalized-${i}.mp4`);
    await downloadHttps(clip.url, file);
    await new Promise((resolve, reject) => ffmpeg(file).setStartTime(clip.startSeconds).duration(clip.endSeconds - clip.startSeconds)
      .videoFilters([`scale=${props.outputWidth}:${props.outputHeight}:force_original_aspect_ratio=decrease`, `pad=${props.outputWidth}:${props.outputHeight}:(ow-iw)/2:(oh-ih)/2`, `fps=${props.fps}`])
      .videoCodec("libx264").audioCodec("aac").outputOptions(["-pix_fmt yuv420p", "-ar 48000", "-ac 2", "-movflags +faststart"])
      .on("end", resolve).on("error", reject).save(target));
    normalized.push(target);
  }
  const listPath = path.join(workDir, "concat.txt");
  await fs.writeFile(listPath, normalized.map(p => `file '${p.replaceAll("'", "'\\''")}'`).join("\n"));
  const joinedPath = path.join(workDir, "joined.mp4");
  await new Promise((resolve, reject) => ffmpeg().input(listPath).inputOptions(["-f concat", "-safe 0"]).outputOptions(["-c copy", "-movflags +faststart"]).on("end", resolve).on("error", reject).save(joinedPath));
  if (!props.audioUrl) { await fs.copyFile(joinedPath, outputPath); return { outputPath, hasAudio: false }; }
  const audioUrl = new URL(props.audioUrl), ext = path.extname(audioUrl.pathname).slice(0, 8) || ".audio", audioPath = path.join(workDir, `music${ext}`);
  await downloadHttps(props.audioUrl, audioPath);
  await new Promise((resolve, reject) => ffmpeg(joinedPath).input(audioPath)
    .complexFilter([`[1:a]volume=${props.audioVolume}[music]`])
    .outputOptions(["-map 0:v:0", "-map 0:a:0?", "-map [music]", "-shortest", "-movflags +faststart", "-pix_fmt yuv420p"])
    .videoCodec("libx264").audioCodec("aac").on("end", resolve).on("error", reject).save(outputPath));
  return { outputPath, hasAudio: true };
}
