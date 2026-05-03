import "server-only";
import { mkdir, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import crypto from "node:crypto";
import { runTriage } from "@/lib/triage";
import { appendThreatRecord } from "@/lib/threats";
import { revalidatePath } from "next/cache";

const MAX_BYTES = 25 * 1024 * 1024; // 25 MB
const ALLOWED_MIME = new Set([
  "image/jpeg",
  "image/png",
  "image/webp",
  "image/gif",
]);

export async function POST(req: Request) {
  let formData: FormData;
  try {
    formData = await req.formData();
  } catch (e) {
    return Response.json(
      { error: `Could not parse multipart body: ${(e as Error).message}` },
      { status: 400 },
    );
  }

  const file = formData.get("image");
  if (!(file instanceof File)) {
    return Response.json(
      { error: "Missing 'image' field (multipart file)." },
      { status: 400 },
    );
  }
  if (file.size === 0) {
    return Response.json({ error: "Empty file." }, { status: 400 });
  }
  if (file.size > MAX_BYTES) {
    return Response.json(
      { error: `File exceeds ${MAX_BYTES} bytes.` },
      { status: 413 },
    );
  }
  if (file.type && !ALLOWED_MIME.has(file.type)) {
    return Response.json(
      { error: `Unsupported mime: ${file.type}` },
      { status: 415 },
    );
  }

  // Persist to a per-request temp file in the OS temp dir.
  const safeExt = path.extname(file.name).toLowerCase().replace(/[^.\w]/g, "") || ".bin";
  const tmpDir = path.join(tmpdir(), "mendacity-intel");
  await mkdir(tmpDir, { recursive: true });
  const id = crypto.randomBytes(8).toString("hex");
  const tmpPath = path.join(tmpDir, `${Date.now()}-${id}${safeExt}`);

  const buf = Buffer.from(await file.arrayBuffer());
  await writeFile(tmpPath, buf);

  try {
    const report = await runTriage(tmpPath);
    const receivedAt = new Date().toISOString();
    const persisted = await appendThreatRecord({
      receivedAt,
      filename: file.name,
      reviewer: process.env.MENDACITY_OPERATOR || "J2-INSCOM-DEMO",
      report,
    }).catch(() => null);
    if (persisted) revalidatePath("/threats");
    return Response.json({
      id: persisted?.id ?? null,
      filename: file.name,
      uploadedAt: receivedAt,
      report,
    });
  } catch (e) {
    return Response.json(
      { error: `Triage failed: ${(e as Error).message}` },
      { status: 500 },
    );
  } finally {
    await rm(tmpPath, { force: true }).catch(() => {});
  }
}
