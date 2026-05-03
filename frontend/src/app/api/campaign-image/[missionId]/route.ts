import "server-only";
import { readFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import path from "node:path";

const REPO_ROOT = path.resolve(
  process.env.MENDACITY_REPO_ROOT ||
    path.join(process.env.HOME || "", "Mendacity"),
);
const GENERATED_DIR = path.join(REPO_ROOT, "missions/generated");
const PYTHON_BIN = process.env.MENDACITY_PYTHON || "python3";

const MID_RE = /^[A-Za-z0-9][A-Za-z0-9_\-]{0,63}$/;

function resolveSafe(missionId: string): string | null {
  if (!MID_RE.test(missionId)) return null;
  const filePath = path.join(GENERATED_DIR, `${missionId}.png`);
  const resolved = path.resolve(filePath);
  if (!resolved.startsWith(GENERATED_DIR + path.sep)) return null;
  return resolved;
}

export async function GET(
  _req: Request,
  ctx: RouteContext<"/api/campaign-image/[missionId]">,
) {
  const { missionId } = await ctx.params;
  const resolved = resolveSafe(missionId);
  if (!resolved) return new Response("Bad mission id", { status: 400 });
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

export async function POST(
  req: Request,
  ctx: RouteContext<"/api/campaign-image/[missionId]">,
) {
  const { missionId } = await ctx.params;
  const resolved = resolveSafe(missionId);
  if (!resolved) {
    return Response.json({ error: "Bad mission id" }, { status: 400 });
  }
  const url = new URL(req.url);
  const op = url.searchParams.get("op");

  if (op === "rotate") {
    const degrees = Number(url.searchParams.get("degrees") || "90");
    if (![90, 180, 270].includes(degrees)) {
      return Response.json({ error: "degrees must be 90/180/270" }, { status: 400 });
    }
    try {
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
    } catch (e) {
      return Response.json({ error: (e as Error).message }, { status: 500 });
    }
  }

  if (op === "regenerate") {
    // Look up the prompt from the campaign DB and re-run image_gen.
    let body: { prompt?: string } = {};
    try {
      body = await req.json();
    } catch {
      // Empty body is fine; we'll fetch the prompt from sqlite.
    }
    let prompt = body.prompt?.trim() || "";
    if (!prompt) {
      // Lazy SQLite fetch; mission id is the campaign suffix.
      try {
        const { execFile } = await import("node:child_process");
        const { promisify } = await import("node:util");
        const execFileP = promisify(execFile);
        const { stdout } = await execFileP("sqlite3", [
          path.join(REPO_ROOT, "social/mendacity.db"),
          "-list",
          `SELECT intent FROM campaign WHERE id='c_${missionId.replace(/'/g, "''")}' LIMIT 1;`,
        ]);
        prompt = stdout.trim();
      } catch {
        prompt = "";
      }
    }
    if (!prompt) {
      return Response.json(
        { error: "Could not resolve prompt for this mission." },
        { status: 400 },
      );
    }
    try {
      await new Promise<void>((resolve, reject) => {
        const child = spawn(
          PYTHON_BIN,
          ["-m", "mendacity.image_gen", "--prompt", prompt, "--output", resolved],
          { cwd: REPO_ROOT, stdio: "ignore" },
        );
        child.on("exit", (code) =>
          code === 0 ? resolve() : reject(new Error(`image_gen exit ${code}`)),
        );
        child.on("error", reject);
      });
      return Response.json({ ok: true, regenerated: true });
    } catch (e) {
      return Response.json({ error: (e as Error).message }, { status: 500 });
    }
  }

  return Response.json({ error: "unknown op (use ?op=rotate or ?op=regenerate)" }, { status: 400 });
}
