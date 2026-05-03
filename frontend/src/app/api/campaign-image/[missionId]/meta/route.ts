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
  ctx: RouteContext<"/api/campaign-image/[missionId]/meta">,
) {
  const { missionId } = await ctx.params;
  if (!MID_RE.test(missionId)) {
    return Response.json({ error: "Bad mission id" }, { status: 400 });
  }
  const filePath = path.resolve(
    path.join(GENERATED_DIR, `${missionId}.meta.json`),
  );
  if (!filePath.startsWith(GENERATED_DIR + path.sep)) {
    return Response.json({ error: "Forbidden" }, { status: 403 });
  }
  try {
    const raw = await readFile(filePath, "utf-8");
    return new Response(raw, {
      status: 200,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return Response.json({ error: "Not generated yet" }, { status: 404 });
  }
}
