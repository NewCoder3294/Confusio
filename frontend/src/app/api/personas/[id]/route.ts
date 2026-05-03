import "server-only";
import { readFile, readdir, unlink } from "node:fs/promises";
import path from "node:path";
import { revalidatePath } from "next/cache";

const REPO_ROOT = path.resolve(
  process.env.MENDACITY_REPO_ROOT ||
    path.join(process.env.HOME || "", "Mendacity"),
);
const PERSONAS_DIR = path.join(REPO_ROOT, "social/personas");

function isSafeId(id: string): boolean {
  return /^[a-z0-9_]{3,40}$/.test(id);
}

async function findReferrers(targetId: string): Promise<string[]> {
  const entries = await readdir(PERSONAS_DIR).catch(() => []);
  const refs: string[] = [];
  for (const f of entries) {
    if (!f.endsWith(".json")) continue;
    if (f === `${targetId}.json`) continue;
    try {
      const raw = await readFile(path.join(PERSONAS_DIR, f), "utf-8");
      const obj = JSON.parse(raw) as Record<string, unknown>;
      const knows = Array.isArray(obj.knows) ? (obj.knows as unknown[]) : [];
      if (knows.includes(targetId)) {
        refs.push(String(obj.id ?? f.replace(/\.json$/, "")));
      }
    } catch {
      // skip unreadable
    }
  }
  return refs;
}

export async function DELETE(
  _req: Request,
  ctx: { params: Promise<{ id: string }> },
) {
  const { id } = await ctx.params;
  if (!isSafeId(id)) {
    return Response.json({ error: "Invalid agent id." }, { status: 400 });
  }

  const target = path.join(PERSONAS_DIR, `${id}.json`);
  const resolved = path.resolve(target);
  if (!resolved.startsWith(path.resolve(PERSONAS_DIR) + path.sep)) {
    return Response.json(
      { error: "Refused: id resolves outside personas dir." },
      { status: 400 },
    );
  }

  const refs = await findReferrers(id);
  if (refs.length > 0) {
    return Response.json(
      {
        error: "Other agents still reference this one in their knows[] graph.",
        referrers: refs,
      },
      { status: 409 },
    );
  }

  try {
    await unlink(target);
  } catch (e) {
    const err = e as NodeJS.ErrnoException;
    if (err.code === "ENOENT") {
      return Response.json(
        { error: `No agent with id "${id}".` },
        { status: 404 },
      );
    }
    return Response.json(
      { error: `delete failed: ${err.message}` },
      { status: 500 },
    );
  }

  revalidatePath("/personas");
  revalidatePath("/");
  return Response.json({ ok: true, deleted: id });
}
