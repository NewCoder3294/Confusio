/**
 * Foundry HTTP client. Server-only — never imported from a Client Component.
 *
 * Token is read from FOUNDRY_TOKEN (no NEXT_PUBLIC_ prefix, so Next.js
 * keeps it server-side). Calls Foundry's Ontology v2 REST surface
 * directly; we don't pull in the JS SDK to keep the dependency footprint
 * small and the demo bundle predictable.
 */

import "server-only";

const HOST = process.env.FOUNDRY_HOST!;
const TOKEN = process.env.FOUNDRY_TOKEN!;
const ONTOLOGY_RID = process.env.FOUNDRY_ONTOLOGY_RID!;

if (!HOST || !TOKEN || !ONTOLOGY_RID) {
  // Surface this loudly during dev — the alternative is silent 401s deep
  // in the rendering tree.
  console.warn(
    "[foundry] Missing env: FOUNDRY_HOST/FOUNDRY_TOKEN/FOUNDRY_ONTOLOGY_RID. Check frontend/.env.local."
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Types — what the operator console actually consumes from Foundry.
// These mirror the Ontology shape we built (palantir/ontology.md, slim
// 4-type version: Channel, Mission, Artifact, DetectionResult).
// ─────────────────────────────────────────────────────────────────────────

export type Mission = {
  missionId: string;
  operator: string;
  status:
    | "draft"
    | "pending_approval"
    | "executing"
    | "completed"
    | "failed"
    | "aborted";
  targetChannelId: string;
  audienceProfile: string;
  artifactPrompt: string;
  dryRun: boolean;
  dispatchedAt: string | null;
  createdAt: string;
  finishedAt: string | null;
  failureCode: string | null;
  provenancePassRate: number | null;
  personaArchetype: string;
  personaNameSeed: string;
  stagesJson: string;
};

export type Artifact = {
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

export type DetectionResult = {
  resultId: string;
  artifactId: string;
  detector: "c2pa" | "titan" | "synthid";
  passed: boolean;
  runStatus: string;
  rawResponse: string;
  checkedAt: string;
};

export type Channel = {
  channel_id: string; // shipped as snake first; see palantir/aip/result_ingester.py
  platform: string;
  displayName: string;
  isSandbox: boolean;
  audienceProfile: string;
  createdAt: string;
};

export type Stage = {
  stage: string;
  status: "ok" | "error" | "skipped";
  ts: string;
  detail: Record<string, unknown>;
  summary?: string;
};

// ─────────────────────────────────────────────────────────────────────────
// Low-level fetch
// ─────────────────────────────────────────────────────────────────────────

async function foundryFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const url = `${HOST.replace(/\/$/, "")}${path}`;
  const cacheOpts: { next?: { revalidate: number }; cache?: "no-store" } =
    init.method && init.method !== "GET" ? { cache: "no-store" } : { next: { revalidate: 5 } };
  const res = await fetch(url, {
    ...init,
    headers: {
      Authorization: `Bearer ${TOKEN}`,
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
    ...cacheOpts,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Foundry ${res.status} on ${path}: ${body.slice(0, 300)}`);
  }
  return (await res.json()) as T;
}

// ─────────────────────────────────────────────────────────────────────────
// Action API — writes
// ─────────────────────────────────────────────────────────────────────────

/**
 * Apply an Ontology action. Action API names are kebab-case
 * (`create-channel`, `edit-channel`, `delete-channel`). Parameters are
 * camelCase except for the manually-added Channel.channel_id (snake) — see
 * project memory `Mendacity Foundry build`.
 */
export async function applyAction(
  actionApiName: string,
  parameters: Record<string, unknown>,
): Promise<unknown> {
  return foundryFetch(
    `/api/v2/ontologies/${ONTOLOGY_RID}/actions/${actionApiName}/apply`,
    {
      method: "POST",
      body: JSON.stringify({ parameters, options: { mode: "VALIDATE_AND_EXECUTE" } }),
    },
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Ontology object listing — paginated
// ─────────────────────────────────────────────────────────────────────────

type ObjectListResponse<T> = {
  data: T[];
  nextPageToken?: string;
};

async function listAll<T>(objectType: string): Promise<T[]> {
  const out: T[] = [];
  let pageToken: string | undefined;
  for (let i = 0; i < 20; i++) {
    const qs = new URLSearchParams({ pageSize: "200" });
    if (pageToken) qs.set("pageToken", pageToken);
    const res = await foundryFetch<ObjectListResponse<T>>(
      `/api/v2/ontologies/${ONTOLOGY_RID}/objects/${objectType}?${qs}`
    );
    out.push(...res.data);
    if (!res.nextPageToken) break;
    pageToken = res.nextPageToken;
  }
  return out;
}

// ─────────────────────────────────────────────────────────────────────────
// Public — typed accessors per object type
// ─────────────────────────────────────────────────────────────────────────

export async function listMissions(): Promise<Mission[]> {
  const rows = await listAll<Record<string, unknown>>("Mission");
  return rows.map(coerceMission).sort((a, b) => b.createdAt.localeCompare(a.createdAt));
}

export async function listArtifacts(): Promise<Artifact[]> {
  const rows = await listAll<Record<string, unknown>>("Artifact");
  return rows.map(coerceArtifact);
}

export async function listDetectionResults(): Promise<DetectionResult[]> {
  const rows = await listAll<Record<string, unknown>>("DetectionResult");
  return rows.map(coerceDetectionResult);
}

export async function listChannels(): Promise<Channel[]> {
  const rows = await listAll<Record<string, unknown>>("Channel");
  return rows.map(coerceChannel);
}

// ─────────────────────────────────────────────────────────────────────────
// Aggregates — one trip down to Foundry, multiple per-mission slices.
// Server components call these once and pass slices into UI sections.
// ─────────────────────────────────────────────────────────────────────────

export type DashboardSnapshot = {
  missions: Mission[];
  artifactByMission: Map<string, Artifact>;
  detectionsByArtifact: Map<string, DetectionResult[]>;
  channelById: Map<string, Channel>;
  fetchedAt: string;
};

export async function getDashboardSnapshot(): Promise<DashboardSnapshot> {
  const [missions, artifacts, detections, channels] = await Promise.all([
    listMissions(),
    listArtifacts(),
    listDetectionResults(),
    listChannels(),
  ]);

  const artifactByMission = new Map<string, Artifact>();
  for (const a of artifacts) artifactByMission.set(a.missionId, a);

  const detectionsByArtifact = new Map<string, DetectionResult[]>();
  for (const d of detections) {
    const arr = detectionsByArtifact.get(d.artifactId) ?? [];
    arr.push(d);
    detectionsByArtifact.set(d.artifactId, arr);
  }
  // Order detections deterministically: c2pa, titan, synthid.
  const detectorOrder: DetectionResult["detector"][] = ["c2pa", "titan", "synthid"];
  for (const arr of detectionsByArtifact.values()) {
    arr.sort(
      (a, b) => detectorOrder.indexOf(a.detector) - detectorOrder.indexOf(b.detector)
    );
  }

  const channelById = new Map<string, Channel>();
  for (const c of channels) channelById.set(c.channel_id, c);

  return {
    missions,
    artifactByMission,
    detectionsByArtifact,
    channelById,
    fetchedAt: new Date().toISOString(),
  };
}

// ─────────────────────────────────────────────────────────────────────────
// Coercion — Foundry returns property names as the API key strings we
// configured (camelCase for everything except Channel.channel_id; see
// palantir/aip/result_ingester.py for why).
// ─────────────────────────────────────────────────────────────────────────

function s(o: Record<string, unknown>, k: string): string {
  const v = o[k];
  return typeof v === "string" ? v : v == null ? "" : String(v);
}
function n(o: Record<string, unknown>, k: string): number | null {
  const v = o[k];
  if (v === null || v === undefined) return null;
  return typeof v === "number" ? v : Number(v);
}
function b(o: Record<string, unknown>, k: string): boolean {
  return Boolean(o[k]);
}
function nullableS(o: Record<string, unknown>, k: string): string | null {
  const v = o[k];
  if (v === null || v === undefined || v === "") return null;
  return typeof v === "string" ? v : String(v);
}

function coerceMission(o: Record<string, unknown>): Mission {
  return {
    missionId: s(o, "missionId"),
    operator: s(o, "operator"),
    status: (s(o, "status") || "draft") as Mission["status"],
    targetChannelId: s(o, "targetChannelId"),
    audienceProfile: s(o, "audienceProfile"),
    artifactPrompt: s(o, "artifactPrompt"),
    dryRun: b(o, "dryRun"),
    dispatchedAt: nullableS(o, "dispatchedAt"),
    createdAt: s(o, "createdAt"),
    finishedAt: nullableS(o, "finishedAt"),
    failureCode: nullableS(o, "failureCode"),
    provenancePassRate: n(o, "provenancePassRate"),
    personaArchetype: s(o, "personaArchetype"),
    personaNameSeed: s(o, "personaNameSeed"),
    stagesJson: s(o, "stagesJson"),
  };
}

function coerceArtifact(o: Record<string, unknown>): Artifact {
  return {
    artifactId: s(o, "artifactId"),
    missionId: s(o, "missionId"),
    prompt: s(o, "prompt"),
    finalPath: s(o, "finalPath"),
    finalSha256: s(o, "finalSha256"),
    passedC2pa: b(o, "passedC2pa"),
    passedTitan: b(o, "passedTitan"),
    passedSynthid: b(o, "passedSynthid"),
    passedAll: b(o, "passedAll"),
    finalProvenanceJson: s(o, "finalProvenanceJson"),
    createdAt: s(o, "createdAt"),
  };
}

function coerceDetectionResult(o: Record<string, unknown>): DetectionResult {
  return {
    resultId: s(o, "resultId"),
    artifactId: s(o, "artifactId"),
    detector: (s(o, "detector") || "c2pa") as DetectionResult["detector"],
    passed: b(o, "passed"),
    runStatus: s(o, "runStatus"),
    rawResponse: s(o, "rawResponse"),
    checkedAt: s(o, "checkedAt"),
  };
}

function coerceChannel(o: Record<string, unknown>): Channel {
  return {
    channel_id: s(o, "channel_id"),
    platform: s(o, "platform"),
    displayName: s(o, "displayName"),
    isSandbox: b(o, "isSandbox"),
    audienceProfile: s(o, "audienceProfile"),
    createdAt: s(o, "createdAt"),
  };
}

// ─────────────────────────────────────────────────────────────────────────
// Stage parsing — `stages_json` on Mission is JSON-encoded.
// ─────────────────────────────────────────────────────────────────────────

export function parseStages(stagesJson: string): Stage[] {
  if (!stagesJson) return [];
  try {
    const parsed = JSON.parse(stagesJson);
    if (Array.isArray(parsed)) return parsed as Stage[];
    return [];
  } catch {
    return [];
  }
}
