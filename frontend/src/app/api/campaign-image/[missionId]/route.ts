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

function resolveSafe(missionId: string, ext: string = "png"): string | null {
  if (!MID_RE.test(missionId)) return null;
  const filePath = path.join(GENERATED_DIR, `${missionId}.${ext}`);
  const resolved = path.resolve(filePath);
  if (!resolved.startsWith(GENERATED_DIR + path.sep)) return null;
  return resolved;
}

export async function GET(
  req: Request,
  ctx: RouteContext<"/api/campaign-image/[missionId]">,
) {
  const { missionId } = await ctx.params;
  const url = new URL(req.url);
  const variantParam = url.searchParams.get("variant");
  // Default variant: the EXIF-transplanted JPEG (camera-realistic).
  // ?variant=raw   → original DALL-E PNG (no metadata, no steg)
  // ?variant=steg  → PNG with LSB-embedded steg payload
  const variant: "default" | "raw" | "steg" =
    variantParam === "raw"
      ? "raw"
      : variantParam === "steg"
        ? "steg"
        : "default";

  const candidates: Array<{ ext: string; mime: string }> =
    variant === "raw"
      ? [{ ext: "png", mime: "image/png" }]
      : variant === "steg"
        ? [{ ext: "steg.png", mime: "image/png" }]
        : [
            { ext: "jpg", mime: "image/jpeg" },
            { ext: "png", mime: "image/png" },
          ];
  for (const c of candidates) {
    const resolved = resolveSafe(missionId, c.ext);
    if (!resolved) continue;
    try {
      const bytes = await readFile(resolved);
      return new Response(new Uint8Array(bytes), {
        status: 200,
        headers: {
          "Content-Type": c.mime,
          "Cache-Control": "no-store",
        },
      });
    } catch {
      // try next candidate
    }
  }
  return new Response("Not generated yet", { status: 404 });
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
    // Rotate the JPG (operator-visible) and also the raw PNG so the steg
    // version stays in sync if the user later switches variant.
    const targets = [
      resolveSafe(missionId, "jpg"),
      resolveSafe(missionId, "png"),
    ].filter((p): p is string => Boolean(p));
    try {
      for (const t of targets) {
        await new Promise<void>((resolve, reject) => {
          const child = spawn(
            PYTHON_BIN,
            ["-m", "forensic.normalize", t, "--rotate", String(degrees), "--force"],
            { cwd: REPO_ROOT, stdio: "ignore" },
          );
          child.on("exit", (code) =>
            code === 0 ? resolve() : reject(new Error(`normalize exit ${code}`)),
          );
          child.on("error", reject);
        });
      }
      return Response.json({ ok: true, rotated: degrees, files: targets.length });
    } catch (e) {
      return Response.json({ error: (e as Error).message }, { status: 500 });
    }
  }

  if (op === "regenerate") {
    let body: { prompt?: string } = {};
    try {
      body = await req.json();
    } catch {
      // Empty body fine — we'll fetch from sqlite.
    }
    let prompt = body.prompt?.trim() || "";
    let channel = "(sandbox)";
    try {
      const { execFile } = await import("node:child_process");
      const { promisify } = await import("node:util");
      const execFileP = promisify(execFile);
      const { stdout } = await execFileP("sqlite3", [
        path.join(REPO_ROOT, "social/mendacity.db"),
        "-list",
        "-separator",
        "|",
        `SELECT intent, channel FROM campaign WHERE id='c_${missionId.replace(/'/g, "''")}' LIMIT 1;`,
      ]);
      const [intent, ch] = stdout.trim().split("|");
      if (!prompt) prompt = (intent || "").trim();
      channel = (ch || channel).trim();
    } catch {
      // best effort
    }
    if (!prompt) {
      return Response.json(
        { error: "Could not resolve prompt for this mission." },
        { status: 400 },
      );
    }
    const png = resolveSafe(missionId, "png");
    if (!png) return Response.json({ error: "Bad mission id" }, { status: 400 });
    try {
      // Re-run the same two-stage chain used at dispatch.
      const cmdLine = [
        PYTHON_BIN,
        "-m",
        "mendacity.image_gen",
        "--prompt",
        JSON.stringify(prompt),
        "--output",
        png,
        "&&",
        PYTHON_BIN,
        "-m",
        "mendacity.process_artifact",
        "--mission-id",
        missionId,
        "--source",
        png,
        "--out-dir",
        path.dirname(png),
        "--channel",
        JSON.stringify(channel),
        "--prompt",
        JSON.stringify(prompt),
      ].join(" ");
      await new Promise<void>((resolve, reject) => {
        const child = spawn("sh", ["-c", cmdLine], {
          cwd: REPO_ROOT,
          stdio: "ignore",
        });
        child.on("exit", (code) =>
          code === 0 ? resolve() : reject(new Error(`regen exit ${code}`)),
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
