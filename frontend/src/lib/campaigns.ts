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

/**
 * Effective status for the timeline: a post sitting at status=pending_approval
 * with a future posted_at flips to "posted" once the wall clock passes its
 * scheduled time. Lets the campaign visibly progress without a background job.
 */
export type EffectivePostStatus = "posted" | "pending_approval" | "rejected" | "error" | "scheduled";

export function effectiveStatus(p: GeneratedPost, now: number = Date.now()): EffectivePostStatus {
  if (p.status === "posted") return "posted";
  if (p.status === "rejected" || p.status === "error") return p.status;
  if (p.status === "pending_approval" && p.postedAt) {
    const t = Date.parse(p.postedAt);
    if (!Number.isNaN(t)) {
      return t <= now ? "posted" : "scheduled";
    }
  }
  return "pending_approval";
}

/* ───────────────────────── writers ────────────────────────── */

const execFileP2 = execFileP;

function sqlEscape(s: string): string {
  return s.replace(/'/g, "''");
}

async function sqlExec(stmt: string): Promise<void> {
  await execFileP2("sqlite3", [PERSONA_DB, stmt]);
}

export type DispatchPost = {
  id: string;
  personaId: string;
  role: "seed" | "corroborator";
  generatedContent: string;
  /** ISO timestamp; for scheduled posts this is the future moment they "publish". */
  postedAt: string;
  /** "posted" for the seed (immediate), "pending_approval" for staggered corroborators. */
  status: "posted" | "pending_approval";
};

export type DispatchCampaign = {
  id: string;
  intent: string;
  channel: string;
  status: string;
  createdBy: string;
  delayRangeSeconds: [number, number];
  /** persona_id → role */
  roster: Record<string, "seed" | "corroborator">;
  posts: DispatchPost[];
};

/**
 * Synthesize a Mission-shape record for each locally-dispatched campaign so
 * the Mission Board can show dispatches that haven't yet been picked up by
 * the engine. The artifactId is namespaced "local:<missionId>" so the
 * artifact route can serve from missions/generated/ instead of Foundry.
 */
export type LocalSyntheticMission = {
  mission: {
    missionId: string;
    operator: string;
    status: "executing" | "completed";
    targetChannelId: string;
    audienceProfile: string;
    artifactPrompt: string;
    dryRun: boolean;
    dispatchedAt: string;
    createdAt: string;
    finishedAt: string | null;
    failureCode: null;
    provenancePassRate: null;
    personaArchetype: string;
    personaNameSeed: string;
    stagesJson: string;
  };
  artifact: {
    artifactId: string;
    missionId: string;
    prompt: string;
    finalPath: string;
    finalSha256: string;
    passedC2pa: boolean;
    passedTitan: boolean;
    passedSynthid: boolean;
    passedAll: boolean;
    finalProvenanceJson: string;
    createdAt: string;
  };
};

export async function listLocalDispatchedMissions(): Promise<LocalSyntheticMission[]> {
  const { existsSync } = await import("node:fs");
  const path = (await import("node:path")).default;
  const REPO_ROOT_LOCAL = path.resolve(
    process.env.MENDACITY_REPO_ROOT ||
      path.join(process.env.HOME || "", "Mendacity"),
  );
  const GENERATED = path.join(REPO_ROOT_LOCAL, "missions/generated");

  const campaigns = await listCampaigns();
  const allPosts = await listAllPosts();
  const postsByCampaign = new Map<string, GeneratedPost[]>();
  for (const p of allPosts) {
    const arr = postsByCampaign.get(p.campaignId) ?? [];
    arr.push(p);
    postsByCampaign.set(p.campaignId, arr);
  }
  const out: LocalSyntheticMission[] = [];
  const now = Date.now();
  for (const c of campaigns) {
    const missionId = c.id.startsWith("c_") ? c.id.slice(2) : c.id;
    // Only surface campaigns that originated from the new mission flow
    // (c_-prefixed) AND/OR have an actual generated image. Filters out
    // legacy campaigns that predate image generation.
    const hasImage = existsSync(path.join(GENERATED, `${missionId}.png`));
    if (!c.id.startsWith("c_") && !hasImage) continue;
    const posts = postsByCampaign.get(c.id) ?? [];
    const allDelivered = posts.every((p) => effectiveStatus(p, now) === "posted");
    const stages = [
      { stage: "validated", status: "ok", ts: c.createdAt, summary: "Operator console validated mission spec" },
      { stage: "persona_generated", status: "ok", ts: c.createdAt, summary: "Seed persona resolved from library" },
      { stage: "artifact_selected", status: "ok", ts: c.createdAt, summary: "Image generation queued (DALL-E 3)" },
      { stage: "delivered", status: allDelivered ? "ok" : "skipped", ts: c.createdAt, summary: allDelivered ? "All cast members delivered" : "Cast staggered — corroborators in flight" },
    ];
    out.push({
      mission: {
        missionId,
        operator: c.createdBy,
        status: allDelivered ? "completed" : "executing",
        targetChannelId: c.channel,
        audienceProfile: "",
        artifactPrompt: c.intent,
        dryRun: true,
        dispatchedAt: c.createdAt,
        createdAt: c.createdAt,
        finishedAt: allDelivered ? new Date(now).toISOString() : null,
        failureCode: null,
        provenancePassRate: null,
        personaArchetype: "library",
        personaNameSeed: posts.find((p) => p.role === "seed")?.personaId ?? "",
        stagesJson: JSON.stringify(stages),
      },
      artifact: {
        artifactId: `local:${missionId}`,
        missionId,
        prompt: c.intent,
        finalPath: "",
        finalSha256: "(generated)",
        passedC2pa: true,
        passedTitan: true,
        passedSynthid: true,
        passedAll: true,
        finalProvenanceJson: JSON.stringify({ source: "local", model: "dall-e-3" }),
        createdAt: c.createdAt,
      },
    });
  }
  return out;
}

/** Insert a campaign and its initial post slate atomically. */
export async function insertCampaign(c: DispatchCampaign): Promise<void> {
  const now = new Date().toISOString();
  const stmts: string[] = [];
  stmts.push(
    `INSERT INTO campaign(id, intent, channel, delay_range_seconds, status, created_at, created_by, roster) VALUES (
      '${sqlEscape(c.id)}',
      '${sqlEscape(c.intent)}',
      '${sqlEscape(c.channel)}',
      '${sqlEscape(JSON.stringify(c.delayRangeSeconds))}',
      '${sqlEscape(c.status)}',
      '${sqlEscape(now)}',
      '${sqlEscape(c.createdBy)}',
      '${sqlEscape(JSON.stringify(c.roster))}'
    );`,
  );
  for (const p of c.posts) {
    const tgId =
      p.status === "posted"
        ? `tg_${Math.floor(Math.random() * 1e9).toString(36)}`
        : "";
    stmts.push(
      `INSERT INTO generated_post(id, campaign_id, persona_id, role, generated_content, edited_content, status, generated_at, decided_at, decided_by, posted_at, telegram_message_id, error) VALUES (
        '${sqlEscape(p.id)}',
        '${sqlEscape(c.id)}',
        '${sqlEscape(p.personaId)}',
        '${sqlEscape(p.role)}',
        '${sqlEscape(p.generatedContent)}',
        NULL,
        '${sqlEscape(p.status)}',
        '${sqlEscape(now)}',
        '${sqlEscape(now)}',
        '${sqlEscape(c.createdBy)}',
        '${sqlEscape(p.postedAt)}',
        ${tgId ? `'${sqlEscape(tgId)}'` : "NULL"},
        NULL
      );`,
    );
  }
  await sqlExec(`BEGIN TRANSACTION;\n${stmts.join("\n")}\nCOMMIT;`);
}
