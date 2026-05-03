import "server-only";
import { readFile, readdir } from "node:fs/promises";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import path from "node:path";

const execFileP = promisify(execFile);

const REPO_ROOT = path.resolve(
  process.env.MENDACITY_REPO_ROOT ||
    path.join(process.env.HOME || "", "Mendacity"),
);
const PERSONAS_DIR = path.join(REPO_ROOT, "social/personas");
const PERSONA_DB = path.join(REPO_ROOT, "social/mendacity.db");

export type Persona = {
  id: string;
  name: string;
  language: string;
  geoAnchor: string;
  bioShort: string;
  backstory: string;
  style: string;
  vocabularyQuirks: string[];
  topicFocus: string[];
  postingSchedule: {
    activeHoursLocal: [number, number];
    avgPostsPerDay: number;
  };
  examples: string[];
  knows: string[];
  sessionPath: string;
};

export type PersonaActivity = {
  postsByStatus: Record<string, number>;
  totalPosts: number;
  lastGeneratedAt: string | null;
  campaigns: Array<{
    id: string;
    intent: string;
    channel: string;
    status: string;
    createdAt: string;
  }>;
};

function coercePersona(o: Record<string, unknown>): Persona {
  const ps = (o.posting_schedule ?? {}) as Record<string, unknown>;
  const hours = (ps.active_hours_local ?? [0, 24]) as [number, number];
  return {
    id: String(o.id ?? ""),
    name: String(o.name ?? ""),
    language: String(o.language ?? ""),
    geoAnchor: String(o.geo_anchor ?? ""),
    bioShort: String(o.bio_short ?? ""),
    backstory: String(o.backstory ?? ""),
    style: String(o.style ?? ""),
    vocabularyQuirks: Array.isArray(o.vocabulary_quirks)
      ? (o.vocabulary_quirks as string[])
      : [],
    topicFocus: Array.isArray(o.topic_focus) ? (o.topic_focus as string[]) : [],
    postingSchedule: {
      activeHoursLocal: hours,
      avgPostsPerDay: Number(ps.avg_posts_per_day ?? 0),
    },
    examples: Array.isArray(o.examples) ? (o.examples as string[]) : [],
    knows: Array.isArray(o.knows) ? (o.knows as string[]) : [],
    sessionPath: String(o.session_path ?? ""),
  };
}

export async function listPersonas(): Promise<Persona[]> {
  const entries = await readdir(PERSONAS_DIR).catch(() => []);
  const out: Persona[] = [];
  for (const f of entries) {
    if (!f.endsWith(".json")) continue;
    try {
      const raw = await readFile(path.join(PERSONAS_DIR, f), "utf-8");
      out.push(coercePersona(JSON.parse(raw)));
    } catch {
      // Skip malformed files rather than crashing the page.
    }
  }
  return out.sort((a, b) => a.name.localeCompare(b.name));
}

async function sqlJson<T = Record<string, unknown>>(query: string): Promise<T[]> {
  try {
    const { stdout } = await execFileP("sqlite3", ["-json", PERSONA_DB, query]);
    const trimmed = stdout.trim();
    if (!trimmed) return [];
    return JSON.parse(trimmed) as T[];
  } catch {
    // DB may be missing entirely (engine not yet active); treat as empty.
    return [];
  }
}

export async function getActivityById(): Promise<Map<string, PersonaActivity>> {
  type StatusRow = { persona_id: string; status: string; c: number };
  type LastRow = { persona_id: string; last_generated: string | null };
  type CampaignRow = {
    persona_id: string;
    id: string;
    intent: string;
    channel: string;
    status: string;
    created_at: string;
  };

  const [statusRows, lastRows, campaignRows] = await Promise.all([
    sqlJson<StatusRow>(
      "SELECT persona_id, status, COUNT(*) c FROM generated_post GROUP BY persona_id, status;",
    ),
    sqlJson<LastRow>(
      "SELECT persona_id, MAX(generated_at) last_generated FROM generated_post GROUP BY persona_id;",
    ),
    sqlJson<CampaignRow>(
      `SELECT DISTINCT gp.persona_id, c.id, c.intent, c.channel, c.status, c.created_at
       FROM generated_post gp JOIN campaign c ON c.id = gp.campaign_id
       ORDER BY c.created_at DESC;`,
    ),
  ]);

  const activity = new Map<string, PersonaActivity>();
  function get(pid: string): PersonaActivity {
    let v = activity.get(pid);
    if (!v) {
      v = {
        postsByStatus: {},
        totalPosts: 0,
        lastGeneratedAt: null,
        campaigns: [],
      };
      activity.set(pid, v);
    }
    return v;
  }

  for (const r of statusRows) {
    const a = get(r.persona_id);
    a.postsByStatus[r.status] = (a.postsByStatus[r.status] ?? 0) + r.c;
    a.totalPosts += r.c;
  }
  for (const r of lastRows) {
    get(r.persona_id).lastGeneratedAt = r.last_generated;
  }
  for (const r of campaignRows) {
    get(r.persona_id).campaigns.push({
      id: r.id,
      intent: r.intent,
      channel: r.channel,
      status: r.status,
      createdAt: r.created_at,
    });
  }
  return activity;
}
