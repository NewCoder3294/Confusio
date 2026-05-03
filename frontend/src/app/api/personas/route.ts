import "server-only";
import { writeFile, mkdir, access } from "node:fs/promises";
import path from "node:path";
import { revalidatePath } from "next/cache";

const REPO_ROOT = path.resolve(
  process.env.MENDACITY_REPO_ROOT ||
    path.join(process.env.HOME || "", "Mendacity"),
);
const PERSONAS_DIR = path.join(REPO_ROOT, "social/personas");

type AgentInput = {
  id: string;
  name: string;
  session_path: string;
  language: string;
  geo_anchor: string;
  bio_short: string;
  backstory: string;
  style: string;
  vocabulary_quirks: string[];
  topic_focus: string[];
  posting_schedule: {
    active_hours_local: [number, number];
    avg_posts_per_day: number;
  };
  examples: string[];
  knows: string[];
};

function arr(v: unknown): string[] {
  if (!Array.isArray(v)) return [];
  return v
    .map((x) => (typeof x === "string" ? x.trim() : ""))
    .filter((x) => x.length > 0);
}

function parseInput(
  o: unknown,
): { ok: true; value: AgentInput } | { ok: false; error: string } {
  if (!o || typeof o !== "object")
    return { ok: false, error: "Body must be JSON object." };
  const r = o as Record<string, unknown>;

  const id = String(r.id ?? "").trim();
  if (!/^[a-z0-9_]{3,40}$/.test(id)) {
    return {
      ok: false,
      error:
        "id must be 3–40 chars, lowercase letters / digits / underscore only.",
    };
  }

  const name = String(r.name ?? "").trim();
  if (!name) return { ok: false, error: "name is required." };

  const language = String(r.language ?? "").trim();
  if (!language) return { ok: false, error: "language is required." };

  const geo_anchor = String(r.geo_anchor ?? "").trim();
  if (!geo_anchor) return { ok: false, error: "geo_anchor is required." };

  const bio_short = String(r.bio_short ?? "").trim();
  if (!bio_short) return { ok: false, error: "bio_short is required." };

  const backstory = String(r.backstory ?? "").trim();
  if (!backstory) return { ok: false, error: "backstory is required." };

  const style = String(r.style ?? "").trim();
  if (!style) return { ok: false, error: "style is required." };

  const ps = (r.posting_schedule ?? {}) as Record<string, unknown>;
  const hours = Array.isArray(ps.active_hours_local)
    ? (ps.active_hours_local as unknown[])
    : [];
  const start = Math.trunc(Number(hours[0] ?? 0));
  const end = Math.trunc(Number(hours[1] ?? 24));
  if (
    !Number.isFinite(start) ||
    !Number.isFinite(end) ||
    start < 0 ||
    start > 23 ||
    end < 1 ||
    end > 24 ||
    start >= end
  ) {
    return {
      ok: false,
      error:
        "active_hours_local must be [start, end] with 0 ≤ start < end ≤ 24.",
    };
  }
  const ppd = Math.trunc(Number(ps.avg_posts_per_day ?? 0));
  if (!Number.isFinite(ppd) || ppd < 0 || ppd > 96) {
    return {
      ok: false,
      error: "avg_posts_per_day must be an integer between 0 and 96.",
    };
  }

  return {
    ok: true,
    value: {
      id,
      name,
      session_path: `sessions/${id}.session`,
      language,
      geo_anchor,
      bio_short,
      backstory,
      style,
      vocabulary_quirks: arr(r.vocabulary_quirks),
      topic_focus: arr(r.topic_focus),
      posting_schedule: {
        active_hours_local: [start, end],
        avg_posts_per_day: ppd,
      },
      examples: arr(r.examples),
      knows: arr(r.knows),
    },
  };
}

async function exists(p: string): Promise<boolean> {
  try {
    await access(p);
    return true;
  } catch {
    return false;
  }
}

export async function POST(req: Request) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return Response.json({ error: "Invalid JSON body." }, { status: 400 });
  }

  const parsed = parseInput(body);
  if (!parsed.ok) return Response.json({ error: parsed.error }, { status: 400 });

  const target = path.join(PERSONAS_DIR, `${parsed.value.id}.json`);
  const resolved = path.resolve(target);
  if (!resolved.startsWith(path.resolve(PERSONAS_DIR) + path.sep)) {
    return Response.json({ error: "Refused: id resolves outside personas dir." }, { status: 400 });
  }
  if (await exists(target)) {
    return Response.json(
      { error: `An agent with id "${parsed.value.id}" already exists.` },
      { status: 409 },
    );
  }

  try {
    await mkdir(PERSONAS_DIR, { recursive: true });
    await writeFile(target, JSON.stringify(parsed.value, null, 2) + "\n", {
      encoding: "utf-8",
      flag: "wx",
    });
  } catch (e) {
    return Response.json(
      { error: `write failed: ${(e as Error).message}` },
      { status: 500 },
    );
  }

  revalidatePath("/personas");
  revalidatePath("/");
  return Response.json({ ok: true, agent: parsed.value });
}
