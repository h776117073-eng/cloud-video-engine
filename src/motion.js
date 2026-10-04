import path from "node:path";
import { bundle } from "@remotion/bundler";
import { renderMedia, selectComposition } from "@remotion/renderer";

let bundleLocationPromise;
async function getBundle() {
  if (!bundleLocationPromise) {
    bundleLocationPromise = bundle({ entryPoint: path.resolve("src/remotion/index.jsx"), webpackOverride: config => config });
  }
  return bundleLocationPromise;
}
export async function renderMotion(props, outputLocation) {
  const serveUrl = await getBundle();
  const inputProps = { ...props };
  const composition = await selectComposition({ serveUrl, id: "MotionScene", browserExecutable: process.env.CHROME_BIN, inputProps });
  const durationInFrames = Math.max(1, Math.round(props.durationSeconds * props.fps));
  await renderMedia({
    composition: { ...composition, width: props.width, height: props.height, fps: props.fps, durationInFrames },
    serveUrl, browserExecutable: process.env.CHROME_BIN, codec: "h264", outputLocation, inputProps,
    pixelFormat: "yuv420p", crf: 18, imageFormat: "jpeg",
    concurrency: Math.max(1, Math.min(4, Number(process.env.RENDER_CONCURRENCY || 2)))
  });
}
