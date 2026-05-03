import "server-only";
import { readFile } from "node:fs/promises";
import path from "node:path";

const REPO_ROOT = path.resolve(
  process.env.MENDACITY_REPO_ROOT ||
    path.join(process.env.HOME || "", "Mendacity"),
);
const GENERATED_DIR = path.join(REPO_ROOT, "missions/generated");

const MID_RE = /^[A-Za-z0-9][A-Za-z0-9_\-]{0,63}$/;

export async function GET(
  _req: Request,
  ctx: RouteContext<"/api/campaign-image/[missionId]">,
) {
  const { missionId } = await ctx.params;
  if (!MID_RE.test(missionId)) {
    return new Response("Bad mission id", { status: 400 });
  }
  const filePath = path.join(GENERATED_DIR, `${missionId}.png`);
  const resolved = path.resolve(filePath);
  if (!resolved.startsWith(GENERATED_DIR + path.sep)) {
    return new Response("Forbidden", { status: 403 });
  }
  try {
    const bytes = await readFile(resolved);
    return new Response(new Uint8Array(bytes), {
      status: 200,
      headers: {
        "Content-Type": "image/png",
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return new Response("Not generated yet", { status: 404 });
  }
}
