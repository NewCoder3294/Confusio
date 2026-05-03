import "server-only";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import path from "node:path";

const execFileP = promisify(execFile);

const REPO_ROOT = path.resolve(
  process.env.MENDACITY_REPO_ROOT ||
    path.join(process.env.HOME || "", "Mendacity"),
);
const PERSONA_DB = path.join(REPO_ROOT, "social/mendacity.db");

export type Campaign = {
  id: string;
  intent: string;
  channel: string;
  status: string;
  createdAt: string;
  createdBy: string;
  delayRangeSeconds: [number, number];
  /** persona_id → role (e.g. seed, corroborator, echo) */
  roster: Record<string, string>;
};

export type GeneratedPost = {
  id: string;
  campaignId: string;
  personaId: string;
  role: string;
  generatedContent: string;
  editedContent: string | null;
  status: string;
  generatedAt: string;
  decidedAt: string | null;
  decidedBy: string | null;
  postedAt: string | null;
  telegramMessageId: string | null;
  error: string | null;
};

async function sqlJson<T = Record<string, unknown>>(query: string): Promise<T[]> {
  try {
    const { stdout } = await execFileP("sqlite3", ["-json", PERSONA_DB, query]);
    const trimmed = stdout.trim();
    if (!trimmed) return [];
    return JSON.parse(trimmed) as T[];
  } catch {
    return [];
  }
}

function safeJson<T>(s: string, fallback: T): T {
  try {
    return JSON.parse(s) as T;
  } catch {
    return fallback;
  }
}

function coerceCampaign(o: Record<string, unknown>): Campaign {
  const delay = safeJson<number[]>(
    String(o.delay_range_seconds ?? "[60, 120]"),
    [60, 120],
  );
  return {
    id: String(o.id ?? ""),
    intent: String(o.intent ?? ""),
    channel: String(o.channel ?? ""),
    status: String(o.status ?? ""),
    createdAt: String(o.created_at ?? ""),
    createdBy: String(o.created_by ?? ""),
    delayRangeSeconds: [delay[0] ?? 60, delay[1] ?? 120],
    roster: safeJson<Record<string, string>>(String(o.roster ?? "{}"), {}),
  };
}

function coercePost(o: Record<string, unknown>): GeneratedPost {
  return {
    id: String(o.id ?? ""),
    campaignId: String(o.campaign_id ?? ""),
    personaId: String(o.persona_id ?? ""),
    role: String(o.role ?? ""),
    generatedContent: String(o.generated_content ?? ""),
    editedContent: o.edited_content == null ? null : String(o.edited_content),
    status: String(o.status ?? ""),
    generatedAt: String(o.generated_at ?? ""),
    decidedAt: o.decided_at == null ? null : String(o.decided_at),
    decidedBy: o.decided_by == null ? null : String(o.decided_by),
    postedAt: o.posted_at == null ? null : String(o.posted_at),
    telegramMessageId:
      o.telegram_message_id == null ? null : String(o.telegram_message_id),
    error: o.error == null ? null : String(o.error),
  };
}

export async function listCampaigns(): Promise<Campaign[]> {
  const rows = await sqlJson<Record<string, unknown>>(
    "SELECT * FROM campaign ORDER BY created_at DESC;",
  );
  return rows.map(coerceCampaign);
}

export async function listPostsForCampaign(
  campaignId: string,
): Promise<GeneratedPost[]> {
  // sqlite3 -separator is awkward to escape from shell; use parameterized via stdin
  const rows = await sqlJson<Record<string, unknown>>(
    `SELECT * FROM generated_post WHERE campaign_id = '${campaignId.replace(/'/g, "''")}' ORDER BY generated_at;`,
  );
  return rows.map(coercePost);
}

export async function listAllPosts(): Promise<GeneratedPost[]> {
  const rows = await sqlJson<Record<string, unknown>>(
    "SELECT * FROM generated_post ORDER BY generated_at DESC;",
  );
  return rows.map(coercePost);
}
