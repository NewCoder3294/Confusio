import "server-only";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import { listArtifacts } from "@/lib/foundry";

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

  const bytes = await readFile(resolved);
  const ext = path.extname(resolved).toLowerCase();
  const mime = MIME[ext] || "application/octet-stream";

  return new Response(new Uint8Array(bytes), {
    status: 200,
    headers: {
      "Content-Type": mime,
      "Content-Length": String(bytes.length),
      // Short cache — mission state is mutable in dev, but the bytes for
      // a given (artifactId, variant) are immutable once written.
      "Cache-Control": "private, max-age=60",
    },
  });
}
