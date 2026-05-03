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
  // Lazy import to avoid the campaigns.ts → personas.ts side-effect graph
  // running for every Foundry-only call site.
  const { listLocalDispatchedMissions } = await import("@/lib/campaigns");

  const [missions, artifacts, detections, channels, local] = await Promise.all([
    listMissions(),
    listArtifacts(),
    listDetectionResults(),
    listChannels(),
    listLocalDispatchedMissions(),
  ]);

  // Merge synthetic local dispatches in front of Foundry data so freshly-
  // dispatched missions show up immediately on the Mission Board.
  const localMissions = local.map((l) => l.mission as Mission);
  const localArtifacts = local.map((l) => l.artifact as Artifact);

  // Demo-pinned synthetic missions: hand-curated entries that aren't backed
  // by a Foundry row or a campaigns-store entry but should appear at the top
  // of the board for the demo. Each entry's image must exist at
  // missions/generated/{missionId}.{png|jpg} so /api/campaign-image/{id} can
  // serve it.
  const demoPins = buildDemoPinnedMissions();
  const demoMissions = demoPins.map((d) => d.mission);
  const demoArtifacts = demoPins.map((d) => d.artifact);

  // Demo pins: ordered list of mission IDs to surface at the top of the
  // board regardless of createdAt. Earlier entries rank higher.
  const PINNED_MISSIONS = [
    "SHADOW-FOX-005", // 01 · B2 bomber
    "SHADOW-FOX-003", // 02 · C-130 wreckage
    "SHADOW-FOX-004", // 03
    "SHADOW-FOX-006", // 04 · desert convoy
    "SHADOW-FOX-007", // 05 · mountain outpost
  ];
  const pinRank = new Map(PINNED_MISSIONS.map((id, i) => [id, i]));
  const allMissions = [...demoMissions, ...localMissions, ...missions].sort((a, b) => {
    const ra = pinRank.get(a.missionId);
    const rb = pinRank.get(b.missionId);
    if (ra !== undefined && rb !== undefined) return ra - rb;
    if (ra !== undefined) return -1;
    if (rb !== undefined) return 1;
    return b.createdAt.localeCompare(a.createdAt);
  });

  const artifactByMission = new Map<string, Artifact>();
  for (const a of artifacts) artifactByMission.set(a.missionId, a);
  for (const a of localArtifacts) artifactByMission.set(a.missionId, a);
  for (const a of demoArtifacts) artifactByMission.set(a.missionId, a);

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
    missions: allMissions,
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

// ─────────────────────────────────────────────────────────────────────────
// Demo-pinned synthetic missions
//
// Hand-curated mission rows that aren't backed by a Foundry record or a
// campaigns-store entry. Each entry's image must already exist at
// `missions/generated/{missionId}.{png|jpg}` so the existing
// `/api/campaign-image/{id}` route can serve it. The artifact uses a
// `local:` prefix so the ArtifactImage component picks the campaign-image
// fetch path.
// ─────────────────────────────────────────────────────────────────────────

type DemoPinnedMission = { mission: Mission; artifact: Artifact };

function buildDemoPinnedMissions(): DemoPinnedMission[] {
  const ts = "2026-05-03T06:00:00+00:00";
  const stages = (channel: string): Stage[] => [
    { stage: "validated", status: "ok", ts, detail: { authority: "title-10", target_class: "foreign", channel } },
    { stage: "persona_generated", status: "ok", ts, detail: { archetype: "library" } },
    { stage: "artifact_selected", status: "ok", ts, detail: { source: "demo-asset" } },
    { stage: "delivered", status: "ok", ts, detail: { channel } },
  ];
  const make = (
    missionId: string,
    channel: string,
    prompt: string,
  ): DemoPinnedMission => ({
    mission: {
      missionId,
      operator: "J2-INSCOM-Demo",
      status: "completed",
      targetChannelId: channel,
      audienceProfile: "",
      artifactPrompt: prompt,
      dryRun: true,
      dispatchedAt: ts,
      createdAt: ts,
      finishedAt: ts,
      failureCode: null,
      provenancePassRate: 1.0,
      personaArchetype: "demo",
      personaNameSeed: "demo-asset",
      stagesJson: JSON.stringify(stages(channel)),
    },
    artifact: {
      artifactId: `local:${missionId}`,
      missionId,
      prompt,
      finalPath: "",
      finalSha256: "(demo)",
      passedC2pa: true,
      passedTitan: true,
      passedSynthid: true,
      passedAll: true,
      finalProvenanceJson: JSON.stringify({ source: "demo", model: "gemini-2.5-flash-image" }),
      createdAt: ts,
    },
  });
  return [
    make(
      "SHADOW-FOX-005",
      "@hackathon_sandbox_alpha",
      "B2 stealth bomber over urban Middle-Eastern district, observational dashcam style",
    ),
    make(
      "SHADOW-FOX-003",
      "@hackathon_sandbox_alpha",
      "C-130 wreckage in mountainous terrain, civilian phone snap, daylight",
    ),
    make(
      "SHADOW-FOX-004",
      "@hackathon_sandbox_alpha",
      "C-130 wreckage close-up frame, fuselage break visible, civilian phone snap",
    ),
    make(
      "SHADOW-FOX-006",
      "@hackathon_sandbox_alpha",
      "Hilltop overwatch frame: armored convoy on a desert road approaching distant compound, dust haze, telephoto",
    ),
    make(
      "SHADOW-FOX-007",
      "@hackathon_sandbox_alpha",
      "Hillside outpost with US flag and sandbag fortification on arid mountainous terrain, telephoto",
    ),
  ];
}

// ─────────────────────────────────────────────────────────────────────────
// Demo-pinned synthetic campaigns
//
// The pinned missions above aren't backed by sqlite campaign rows, so the
// Mission Board's CAST / POSTS / INJECTION tabs would otherwise be hidden
// for them. Surface a hand-curated roster + posts so every pin renders the
// same tab set as a live dispatched mission.
// ─────────────────────────────────────────────────────────────────────────

import type { Campaign, GeneratedPost } from "@/lib/campaigns";

type DemoPinnedCampaign = { campaign: Campaign; posts: GeneratedPost[] };

export function buildDemoPinnedCampaigns(): DemoPinnedCampaign[] {
  const channel = "@hackathon_sandbox_alpha";
  const ts = "2026-05-03T06:00:00+00:00";
  const tsSeed = "2026-05-03T06:00:30+00:00";
  const tsB = "2026-05-03T06:02:10+00:00";
  const tsC = "2026-05-03T06:04:45+00:00";

  const pin = (
    missionId: string,
    intent: string,
    seed: string,
    cor1: string,
    cor2: string,
    seedText: string,
    cor1Text: string,
    cor2Text: string,
  ): DemoPinnedCampaign => {
    const cid = `c_${missionId}`;
    const roster: Record<string, string> = {
      [seed]: "seed",
      [cor1]: "corroborator",
      [cor2]: "corroborator",
    };
    const post = (
      pid: string,
      role: "seed" | "corroborator",
      content: string,
      generatedAt: string,
      msgId: string,
    ): GeneratedPost => ({
      id: `p_${missionId}_${pid}`,
      campaignId: cid,
      personaId: pid,
      role,
      generatedContent: content,
      editedContent: null,
      status: "posted",
      generatedAt,
      decidedAt: generatedAt,
      decidedBy: "auto-approve",
      postedAt: generatedAt,
      telegramMessageId: msgId,
      error: null,
    });
    return {
      campaign: {
        id: cid,
        intent,
        channel,
        status: "completed",
        createdAt: ts,
        createdBy: "J2-INSCOM-Demo",
        delayRangeSeconds: [60, 120],
        roster,
      },
      posts: [
        post(seed, "seed", seedText, tsSeed, "1001"),
        post(cor1, "corroborator", cor1Text, tsB, "1002"),
        post(cor2, "corroborator", cor2Text, tsC, "1003"),
      ],
    };
  };

  return [
    pin(
      "SHADOW-FOX-005",
      "Surface a B2 sortie sighting over a foreign urban district to seed open-source attribution.",
      "news_aggregator",
      "anton_kh",
      "dmitry_dn",
      "URGENT — unconfirmed dashcam frame circulating from the eastern district. Looks like a B-2. Verifying source.",
      "Я тоже это видел из машины, прошёл низко прямо над магистралью. Никто не сирену не включал.",
      "Сусід зняв з балкона — те саме літак. Ніяких новин по телебаченню досі.",
    ),
    pin(
      "SHADOW-FOX-003",
      "Civilian discovery of downed C-130 in mountainous terrain — propagate locator imagery.",
      "anton_kh",
      "olga_kyiv",
      "news_aggregator",
      "Нашёл обломки самолёта на склоне у трассы М-04. Бортовой номер не разобрать, фюзеляж сломан.",
      "Я з вікна квартири бачу дим над пагорбом. Це у напрямку, де Антон знімав.",
      "Aggregating: civilian-sourced wreckage frames east of M-04 ridge. Cross-checking against tail-number registries.",
    ),
    pin(
      "SHADOW-FOX-004",
      "Tighter close-up of the C-130 fuselage break — reinforce 003 with second angle.",
      "anton_kh",
      "dmitry_dn",
      "news_aggregator",
      "Підійшов ближче. Розлом по фюзеляжу видно чітко. Тут нікого з рятувальників ще немає.",
      "Это тот же борт, что Антон. Я подъехал по другой дороге, дым ещё стоит.",
      "Second angle from the same wreckage site. Frames consistent with first report. Tail markings still illegible.",
    ),
    pin(
      "SHADOW-FOX-006",
      "Surface a hilltop overwatch frame of an armored convoy approaching a distant compound.",
      "news_aggregator",
      "anton_kh",
      "olga_kyiv",
      "Telephoto frame from a ridgeline observer: armored column moving on the desert track toward the compound. Dust haze rising.",
      "Сверху видно лучше — колонна не разворачивается, идёт прямиком к комплексу.",
      "Я не там, але збільшила зображення — це точно бронетранспортери, не цивільні.",
    ),
    pin(
      "SHADOW-FOX-007",
      "Hillside outpost frame: US flag + sandbag fortification on arid mountain terrain.",
      "anton_kh",
      "news_aggregator",
      "dmitry_dn",
      "Зняв з паралельного хребта телеоб'єктивом. Прапор США, мішки з піском, позиція явно облаштована.",
      "Frame consistent with several earlier observer posts in the area. Geotag check pending.",
      "Вижу на фото знакомые ящики — это та же позиция, что я видел в прошлом месяце.",
    ),
  ];
}
