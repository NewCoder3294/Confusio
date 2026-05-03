import "server-only";
import { readFile, stat } from "node:fs/promises";
import { spawn } from "node:child_process";
import path from "node:path";
import { listArtifacts } from "@/lib/foundry";

const REPO_ROOT = path.resolve(
  process.env.MENDACITY_REPO_ROOT ||
    path.join(process.env.HOME || "", "Mendacity"),
);
const PYTHON_BIN = process.env.MENDACITY_PYTHON || "python3";

/**
 * One-shot orientation normalization. Idempotent — `forensic.normalize`
 * writes a `.normalized` marker and short-circuits on subsequent runs, so
 * this is fast (<10ms) for already-normalized files.
 */
async function normalizeOnDisk(filePath: string): Promise<void> {
  await new Promise<void>((resolve) => {
    const child = spawn(
      PYTHON_BIN,
      ["-m", "forensic.normalize", filePath],
      { cwd: REPO_ROOT, stdio: "ignore" },
    );
    const finish = () => resolve();
    child.on("exit", finish);
    child.on("error", finish);
    // Hard cap so a hung subprocess never blocks an artifact load.
    setTimeout(finish, 1500);
  });
}

const ROOT = path.resolve(
  process.env.MENDACITY_ARTIFACTS_ROOT ||
    path.join(process.env.HOME || "", "Mendacity/missions/work"),
);

const VARIANTS = ["clean", "source", "stripped"] as const;
type Variant = (typeof VARIANTS)[number];

const MIME: Record<string, string> = {
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".png": "image/png",
  ".webp": "image/webp",
  ".gif": "image/gif",
};

// The engine sometimes writes PNG bytes into a file named .jpg (the source
// variant from generators like Gemini). Sniff the magic bytes so the browser
// gets the right Content-Type regardless of extension.
function sniffMime(b: Buffer): string | null {
  if (b.length >= 8 && b[0] === 0x89 && b[1] === 0x50 && b[2] === 0x4e && b[3] === 0x47) return "image/png";
  if (b.length >= 3 && b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff) return "image/jpeg";
  if (b.length >= 12 && b[0] === 0x52 && b[1] === 0x49 && b[2] === 0x46 && b[3] === 0x46 && b[8] === 0x57 && b[9] === 0x45 && b[10] === 0x42 && b[11] === 0x50) return "image/webp";
  if (b.length >= 6 && b[0] === 0x47 && b[1] === 0x49 && b[2] === 0x46) return "image/gif";
  return null;
}

export async function GET(
  req: Request,
  ctx: RouteContext<"/api/artifact/[artifactId]">,
) {
  const { artifactId } = await ctx.params;
  const url = new URL(req.url);
  const variantParam = url.searchParams.get("variant");
  const variant: Variant = VARIANTS.includes(variantParam as Variant)
    ? (variantParam as Variant)
    : "clean";

  const artifacts = await listArtifacts();
  const artifact = artifacts.find((a) => a.artifactId === artifactId);
  if (!artifact || !artifact.finalPath) {
    return new Response("Not found", { status: 404 });
  }

  // The finalPath we got from Foundry is the "clean" variant. Source/stripped
  // live next to it under the engine's mission convention.
  const cleanPath = artifact.finalPath;
  const dir = path.dirname(cleanPath);
  const filePath =
    variant === "clean"
      ? cleanPath
      : path.join(dir, `artifact_${variant}.jpg`);

  const resolved = path.resolve(filePath);
  if (resolved !== ROOT && !resolved.startsWith(ROOT + path.sep)) {
    // Path escapes the allowed artifact root — refuse.
    return new Response("Forbidden", { status: 403 });
  }

  let info;
  try {
    info = await stat(resolved);
  } catch {
    return new Response("Not on disk", { status: 404 });
  }
  if (!info.isFile()) {
    return new Response("Not a file", { status: 404 });
  }

  await normalizeOnDisk(resolved);
  const bytes = await readFile(resolved);
  const ext = path.extname(resolved).toLowerCase();
  const mime = sniffMime(bytes) || MIME[ext] || "application/octet-stream";

  return new Response(new Uint8Array(bytes), {
    status: 200,
    headers: {
      "Content-Type": mime,
      "Content-Length": String(bytes.length),
      // No cache — operator may rotate the file via the rotate route and we
      // want the next image render to reflect that immediately.
      "Cache-Control": "no-store",
    },
  });
}

export async function POST(
  req: Request,
  ctx: RouteContext<"/api/artifact/[artifactId]">,
) {
  const { artifactId } = await ctx.params;
  const url = new URL(req.url);
  const variantParam = url.searchParams.get("variant");
  const variant: Variant = VARIANTS.includes(variantParam as Variant)
    ? (variantParam as Variant)
    : "clean";
  const degrees = Number(url.searchParams.get("degrees") || "90");
  if (![90, 180, 270].includes(degrees)) {
    return Response.json({ error: "degrees must be 90, 180, or 270" }, { status: 400 });
  }

  const artifacts = await listArtifacts();
  const artifact = artifacts.find((a) => a.artifactId === artifactId);
  if (!artifact || !artifact.finalPath) {
    return Response.json({ error: "Not found" }, { status: 404 });
  }
  const cleanPath = artifact.finalPath;
  const dir = path.dirname(cleanPath);
  const filePath =
    variant === "clean"
      ? cleanPath
      : path.join(dir, `artifact_${variant}.jpg`);
  const resolved = path.resolve(filePath);
  if (resolved !== ROOT && !resolved.startsWith(ROOT + path.sep)) {
    return Response.json({ error: "Forbidden" }, { status: 403 });
  }

  await new Promise<void>((resolve, reject) => {
    const child = spawn(
      PYTHON_BIN,
      ["-m", "forensic.normalize", resolved, "--rotate", String(degrees), "--force"],
      { cwd: REPO_ROOT, stdio: "ignore" },
    );
    child.on("exit", (code) =>
      code === 0 ? resolve() : reject(new Error(`normalize exit ${code}`)),
    );
    child.on("error", reject);
  });

  return Response.json({ ok: true, rotated: degrees });
}
