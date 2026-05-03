/**
 * Headless runner for samukingx/SynthIDBye imageProcessor (same logic as the web UI).
 * Reads an image with sharp, runs removeAllAIWatermarks, writes JPEG.
 *
 *   npx tsx scripts/synthidbye_run.ts <input> <output.jpg>
 *
 * Requires: npm install (repo root), vendor/SynthIDBye from upstream clone.
 */
import "./node_imagedata_polyfill.ts";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

import { removeAllAIWatermarks } from "../vendor/SynthIDBye/src/utils/imageProcessor.ts";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

async function main() {
  const inp = process.argv[2];
  const outp = process.argv[3];
  if (!inp || !outp) {
    console.error(
      "Usage: npx tsx scripts/synthidbye_run.ts <input_image> <output.jpg>",
    );
    process.exit(1);
  }

  const vendorTs = path.join(
    __dirname,
    "../vendor/SynthIDBye/src/utils/imageProcessor.ts",
  );
  if (!fs.existsSync(vendorTs)) {
    console.error(
      "Missing vendor/SynthIDBye. Clone with:\n  git clone https://github.com/samukingx/SynthIDBye.git vendor/SynthIDBye",
    );
    process.exit(1);
  }

  const { data, info } = await sharp(inp)
    .ensureAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true });

  const w = info.width;
  const h = info.height;
  const rgba = new Uint8ClampedArray(
    data.buffer,
    data.byteOffset,
    data.byteLength,
  );

  const imageData = {
    data: rgba,
    width: w,
    height: h,
    colorSpace: "srgb",
  } as ImageData;

  const { imageData: processed, seed } = removeAllAIWatermarks(
    imageData,
    undefined,
    "high",
  );

  await sharp(Buffer.from(processed.data), {
    raw: { width: w, height: h, channels: 4 },
  })
    .jpeg({ quality: 85 })
    .toFile(outp);

  console.error("SynthIDBye seed (save if you need reversibility notes):", seed);
  console.error("Wrote", outp);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
