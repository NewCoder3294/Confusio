import Link from "next/link";
import {
  getDashboardSnapshot,
  listChannels,
  parseStages,
  type Mission,
  type Channel,
  type Artifact,
  type DetectionResult,
  type Stage,
} from "@/lib/foundry";
import { listPersonas, type Persona } from "@/lib/personas";
import {
  listCampaigns,
  listAllPosts,
  type Campaign,
  type GeneratedPost,
} from "@/lib/campaigns";
import { StatusPill } from "@/components/status-pill";
import { DetectorPill } from "@/components/detector-pill";
import { Card, Tabs, Block, Row, PageHeader } from "@/components/surfaces";
import { DispatchButton } from "@/components/dispatch-button";
import { AutoRefresh } from "@/components/auto-refresh";
import { ArtifactImage } from "@/components/artifact-image";
import {
  CastPanel,
  PostsPanel,
  InjectionPanel,
  buildCampaignEvents,
  type TimelineEvent,
} from "@/components/campaign-tabs";

type ArtifactVariant = "source" | "stripped" | "clean";

export default async function MissionBoardPage({
  searchParams,
}: {
  searchParams: Promise<{ [k: string]: string | string[] | undefined }>;
}) {
  const sp = await searchParams;
  const selectedId = typeof sp.m === "string" ? sp.m : undefined;
  const variantParam = typeof sp.v === "string" ? sp.v : undefined;
  const variant: ArtifactVariant =
    variantParam === "source" || variantParam === "stripped"
      ? variantParam
      : "clean";

  const [snap, allChannels, personas, campaigns, allPosts] = await Promise.all([
    getDashboardSnapshot(),
    listChannels(),
    listPersonas(),
    listCampaigns(),
    listAllPosts(),
  ]);
  const selected =
    snap.missions.find((m) => m.missionId === selectedId) ?? snap.missions[0];

  const personasById = new Map(personas.map((p) => [p.id, p]));
  const campaignByMissionId = new Map<string, Campaign>();
  for (const c of campaigns) {
    const mid = c.id.startsWith("c_") ? c.id.slice(2) : c.id;
    campaignByMissionId.set(mid, c);
  }
  const postsByCampaignId = new Map<string, GeneratedPost[]>();
  for (const p of allPosts) {
    const arr = postsByCampaignId.get(p.campaignId) ?? [];
    arr.push(p);
    postsByCampaignId.set(p.campaignId, arr);
  }

  const counts = computeCounts(snap.missions);
  const sandboxChannels = allChannels
    .filter((c) => c.isSandbox)
    .sort((a, b) => a.displayName.localeCompare(b.displayName))
    .map((c) => ({
      id: c.channel_id || c.displayName,
      displayName: c.displayName,
      audienceProfile: c.audienceProfile,
    }))
    .filter((c) => c.id);
  const personaLite = personas.map((p) => ({
    id: p.id,
    name: p.name,
    language: p.language,
    geoAnchor: p.geoAnchor,
    bioShort: p.bioShort,
    knows: p.knows,
  }));

  return (
    <>
      <AutoRefresh intervalMs={6000} />
      <PageHeader
        eyebrow="Title 10 §1631 — Mission ledger · Append-only audit trail"
        title="Mission Board"
        brief="Live record of every dispatched attack chain. Pick a mission to inspect its artifact, detector verdicts, and stage timeline."
        actions={
          <div className="flex items-stretch gap-2">
            <MiniStat label="Active" value={counts.active} tone="info" />
            <MiniStat label="Done 24h" value={counts.completed} tone="pass" />
            <MiniStat label="Failed" value={counts.failed} tone="fail" />
            <MiniStat
              label="Pass rate"
              value={
                counts.recentPassRate === null
                  ? "—"
                  : `${Math.round(counts.recentPassRate * 100)}%`
              }
            />
            <DispatchButton
              channels={sandboxChannels}
              personas={personaLite}
            />
          </div>
        }
      />

      <div className="flex-1 min-h-0 w-full mx-auto px-6 py-3 grid grid-cols-[280px_1fr] gap-3">
        <Card title="Missions" meta={`${snap.missions.length}`}>
          <MissionList
            missions={snap.missions}
            selectedId={selected?.missionId}
            channelById={snap.channelById}
          />
        </Card>

        {selected ? (
          <MissionDetail
            mission={selected}
            channel={snap.channelById.get(selected.targetChannelId)}
            artifact={snap.artifactByMission.get(selected.missionId)}
            detections={
              snap.artifactByMission.get(selected.missionId)
                ? snap.detectionsByArtifact.get(
                    snap.artifactByMission.get(selected.missionId)!.artifactId,
                  ) ?? []
                : []
            }
            variant={variant}
            campaign={campaignByMissionId.get(selected.missionId)}
            posts={
              campaignByMissionId.get(selected.missionId)
                ? postsByCampaignId.get(
                    campaignByMissionId.get(selected.missionId)!.id,
                  ) ?? []
                : []
            }
            personasById={personasById}
          />
        ) : (
          <Card title="No mission selected">
            <div className="px-4 py-8 text-fg-faint italic text-[12px] text-center">
              Pick a mission from the left.
            </div>
          </Card>
        )}
      </div>
    </>
  );
}

/* ─────────────────────────────────────────────────────────────────────── */

function computeCounts(missions: Mission[]) {
  const now = Date.now();
  const active = missions.filter((m) => m.status === "executing").length;
  const dayAgo = now - 24 * 60 * 60 * 1000;
  const completed = missions.filter(
    (m) =>
      m.status === "completed" &&
      m.finishedAt &&
      Date.parse(m.finishedAt) >= dayAgo,
  ).length;
  const failed = missions.filter(
    (m) => m.status === "failed" || m.status === "aborted",
  ).length;
  const lastFive = missions
    .filter((m) => m.status === "completed" && m.provenancePassRate !== null)
    .slice(0, 5);
  const recentPassRate =
    lastFive.length === 0
      ? null
      : lastFive.reduce((acc, m) => acc + (m.provenancePassRate ?? 0), 0) /
        lastFive.length;
  return { active, completed, failed, recentPassRate };
}

function MissionList({
  missions,
  selectedId,
  channelById,
}: {
  missions: Mission[];
  selectedId: string | undefined;
  channelById: Map<string, Channel>;
}) {
  if (missions.length === 0) {
    return (
      <div className="px-4 py-6 text-fg-faint italic text-[12px]">
        No missions yet.
      </div>
    );
  }
  return (
    <ol>
      {missions.map((m) => {
        const channel = channelById.get(m.targetChannelId);
        const isSelected = m.missionId === selectedId;
        return (
          <li key={m.missionId}>
            <Link
              href={{ pathname: "/", query: { m: m.missionId } }}
              scroll={false}
              className={`block px-3 py-2 border-b border-border-subtle hover:bg-bg-hover transition-colors ${
                isSelected
                  ? "bg-bg-elevated border-l-2 border-l-info-fg"
                  : "border-l-2 border-l-transparent"
              }`}
            >
              <div className="flex items-baseline justify-between gap-2">
                <span className="font-mono text-[11px] text-fg-default truncate">
                  {m.missionId}
                </span>
                <StatusPill status={m.status} />
              </div>
              <div className="mt-1 text-[10px] text-fg-faint truncate">
                {channel?.displayName ?? m.targetChannelId}
              </div>
            </Link>
          </li>
        );
      })}
    </ol>
  );
}

function MissionDetail({
  mission,
  channel,
  artifact,
  detections,
  variant,
  campaign,
  posts,
  personasById,
}: {
  mission: Mission;
  channel: Channel | undefined;
  artifact: Artifact | undefined;
  detections: DetectionResult[];
  variant: ArtifactVariant;
  campaign: Campaign | undefined;
  posts: GeneratedPost[];
  personasById: Map<string, Persona>;
}) {
  const stages = parseStages(mission.stagesJson);
  const campaignEvents: TimelineEvent[] = campaign
    ? buildCampaignEvents(campaign, posts, personasById)
    : [];

  const meta = (
    <span className="flex items-baseline gap-3">
      <StatusPill status={mission.status} />
      {mission.dryRun && (
        <span className="font-mono text-[9px] tracking-[0.16em] text-fg-faint border border-border-default px-2 py-[1px]">
          DRY RUN
        </span>
      )}
    </span>
  );

  return (
    <Card title={mission.missionId} meta="">
      {/* meta is rendered below as a header strip; Card's meta slot is small */}
      <div className="px-4 py-2 border-b border-border-subtle bg-bg-base flex items-baseline justify-between gap-3">
        <div className="flex items-baseline gap-3">{meta}</div>
        <span className="font-mono text-[10px] text-fg-faint">
          {mission.dispatchedAt ? `dispatched ${formatRelative(mission.dispatchedAt)}` : ""}
        </span>
      </div>

      <Tabs
        tabs={[
          {
            id: "summary",
            label: "Summary",
            panel: (
              <SummaryPanel
                mission={mission}
                channel={channel}
                artifact={artifact}
              />
            ),
          },
          {
            id: "artifact",
            label: "Artifact",
            panel: (
              <ArtifactPanel
                artifact={artifact}
                mission={mission}
                variant={variant}
              />
            ),
          },
          ...(campaign
            ? [
                {
                  id: "cast",
                  label: "Cast",
                  count: Object.keys(campaign.roster).length,
                  panel: (
                    <CastPanel
                      campaign={campaign}
                      personasById={personasById}
                    />
                  ),
                },
                {
                  id: "posts",
                  label: "Posts",
                  count: posts.length,
                  panel: (
                    <PostsPanel posts={posts} personasById={personasById} />
                  ),
                },
                {
                  id: "injection",
                  label: "Injection",
                  panel: <InjectionPanel missionId={mission.missionId} />,
                },
              ]
            : []),
          {
            id: "provenance",
            label: "Provenance",
            count: detections.length,
            panel: <ProvenancePanel detections={detections} artifact={artifact} />,
          },
          {
            id: "timeline",
            label: "Timeline",
            count: stages.length + campaignEvents.length,
            panel: (
              <TimelinePanel
                stages={stages}
                campaignEvents={campaignEvents}
              />
            ),
          },
          {
            id: "raw",
            label: "Raw",
            panel: <RawPanel artifact={artifact} mission={mission} />,
          },
        ]}
      />
    </Card>
  );
}

/* ─────────────────────────────────────────────────────────────────────── */
/* Panels                                                                    */
/* ─────────────────────────────────────────────────────────────────────── */

function SummaryPanel({
  mission,
  channel,
  artifact,
}: {
  mission: Mission;
  channel: Channel | undefined;
  artifact: Artifact | undefined;
}) {
  return (
    <>
      <Block label="Target">
        <dl>
          <Row
            label="Channel"
            value={channel?.displayName ?? mission.targetChannelId}
            mono
          />
          <Row
            label="Audience"
            value={
              mission.audienceProfile ||
              channel?.audienceProfile ||
              "(no profile)"
            }
          />
          <Row label="Operator" value={mission.operator} mono />
        </dl>
      </Block>
      <Block label="Persona">
        <dl>
          <Row
            label="Archetype"
            value={mission.personaArchetype || "—"}
          />
          <Row label="Name seed" value={mission.personaNameSeed || "—"} />
        </dl>
      </Block>
      {artifact && (
        <Block label="Brief">
          <p className="text-[12px] leading-6 text-fg-default">
            {summarizeArtifact(artifact)}
          </p>
        </Block>
      )}
      {mission.status === "failed" && mission.failureCode && (
        <Block label="Failure">
          <div className="font-mono text-[12px] text-fail-fg">
            {mission.failureCode}
          </div>
        </Block>
      )}
    </>
  );
}

function ProvenancePanel({
  detections,
  artifact,
}: {
  detections: DetectionResult[];
  artifact: Artifact | undefined;
}) {
  if (detections.length === 0) {
    return (
      <div className="px-4 py-6 text-fg-faint italic text-[12px]">
        No detector results recorded.
      </div>
    );
  }
  return (
    <>
      <Block label="Detector verdicts">
        <div className="grid grid-cols-3 gap-2">
          {detections.map((d) => (
            <DetectorPill key={d.resultId} d={d} />
          ))}
        </div>
      </Block>
      {artifact && (
        <Block label="Composite">
          <Row
            label="All passed"
            value={
              <span
                className={
                  artifact.passedAll ? "text-pass-fg" : "text-fail-fg"
                }
              >
                {artifact.passedAll ? "yes" : "no"}
              </span>
            }
            mono
          />
          <Row
            label="C2PA"
            value={artifact.passedC2pa ? "pass" : "fail"}
            mono
          />
          <Row
            label="Titan"
            value={artifact.passedTitan ? "pass" : "fail"}
            mono
          />
          <Row
            label="SynthID"
            value={artifact.passedSynthid ? "pass" : "fail"}
            mono
          />
        </Block>
      )}
      <Block>
        <p className="text-[10px] text-fg-faint italic">
          Detectors are run on the offensive side as self-grading: artifacts
          that flag here would not survive an adversary&apos;s vetting pipeline.
        </p>
      </Block>
    </>
  );
}

function ArtifactPanel({
  artifact,
  mission,
  variant,
}: {
  artifact: Artifact | undefined;
  mission: Mission;
  variant: ArtifactVariant;
}) {
  if (!artifact) {
    return (
      <div className="px-4 py-6 text-fg-faint italic text-[12px]">
        No artifact recorded for this mission.
      </div>
    );
  }
  const VARIANT_COPY: Record<ArtifactVariant, { label: string; sub: string }> = {
    source: { label: "SOURCE", sub: "Generator output, watermarks intact" },
    stripped: { label: "STRIPPED", sub: "Watermarks removed" },
    clean: { label: "CLEAN", sub: "EXIF transplanted, ships" },
  };
  const copy = VARIANT_COPY[variant];

  return (
    <>
      {artifact.artifactId.startsWith("local:") ? (
        <ArtifactImage
          localMissionId={artifact.artifactId.slice(6)}
          prompt={artifact.prompt}
          alt={`Mission ${mission.missionId} artifact`}
        />
      ) : (
        <ArtifactImage
          artifactId={artifact.artifactId}
          variant={variant}
          alt={`Mission ${mission.missionId} artifact (${variant})`}
        />
      )}
      <Block>
        <div className="flex items-baseline justify-between gap-3">
          <div>
            <div className="font-mono text-[11px] tracking-[0.16em] text-fg-default">
              {copy.label}
            </div>
            <div className="text-[10px] text-fg-faint italic mt-[1px]">
              {copy.sub}
            </div>
          </div>
          <ArtifactVariantSwitcher
            missionId={mission.missionId}
            current={variant}
          />
        </div>
      </Block>
      <Block label="Metadata">
        <dl>
          <Row label="Prompt" value={artifact.prompt} />
          <Row label="Path" value={artifact.finalPath} mono />
          <Row
            label="SHA-256"
            value={artifact.finalSha256.slice(0, 32) + "…"}
            mono
          />
        </dl>
      </Block>
    </>
  );
}

function TimelinePanel({
  stages,
  campaignEvents,
}: {
  stages: Stage[];
  campaignEvents: TimelineEvent[];
}) {
  if (stages.length === 0 && campaignEvents.length === 0) {
    return (
      <div className="px-4 py-6 text-fg-faint italic text-[12px]">
        No timeline events recorded.
      </div>
    );
  }
  const STAGE_ICON: Record<string, string> = { ok: "✓", skipped: "·", error: "✗" };
  const STAGE_TONE: Record<string, string> = {
    ok: "text-pass-fg",
    skipped: "text-fg-faint",
    error: "text-fail-fg",
  };
  const STAGE_LABEL: Record<string, string> = {
    validated: "VALIDATED",
    persona_generated: "PERSONA FORGED",
    artifact_selected: "ARTIFACT SELECTED",
    watermark_strip: "WATERMARK STRIPPED",
    exif_transplant: "EXIF TRANSPLANTED",
    provenance_check: "PROVENANCE GRADED",
    delivered: "DELIVERY",
  };
  const CAMPAIGN_TONE: Record<TimelineEvent["tone"], string> = {
    info: "text-info-fg",
    pass: "text-pass-fg",
    warn: "text-warn-fg",
    fail: "text-fail-fg",
    neutral: "text-fg-muted",
  };
  const CAMPAIGN_ICON: Record<TimelineEvent["tone"], string> = {
    info: "→",
    pass: "✓",
    warn: "·",
    fail: "✗",
    neutral: "·",
  };

  // Merge stages + campaign events by timestamp, ascending. Stages may have
  // missing/empty ts; sort those to the start.
  type Item =
    | { kind: "stage"; ts: string; data: Stage }
    | { kind: "event"; ts: string; data: TimelineEvent };
  const items: Item[] = [
    ...stages.map((s) => ({ kind: "stage" as const, ts: s.ts ?? "", data: s })),
    ...campaignEvents.map((e) => ({
      kind: "event" as const,
      ts: e.ts,
      data: e,
    })),
  ].sort((a, b) => a.ts.localeCompare(b.ts));

  return (
    <ol>
      {items.map((it, i) => {
        if (it.kind === "stage") {
          const s = it.data;
          const tone = s.status ?? "ok";
          return (
            <li
              key={`stage-${s.stage}-${i}`}
              className="grid grid-cols-[24px_180px_72px_1fr] items-baseline gap-3 px-4 py-2 border-b border-border-subtle last:border-b-0"
            >
              <span className={`font-mono text-base ${STAGE_TONE[tone] ?? "text-fg-muted"}`}>
                {STAGE_ICON[tone] ?? "·"}
              </span>
              <span className="font-mono text-[11px] tracking-[0.12em] text-fg-default">
                {STAGE_LABEL[s.stage] ?? s.stage.toUpperCase()}
              </span>
              <span className="font-mono text-[10px] text-fg-faint tabular-nums">
                {s.ts ? new Date(s.ts).toISOString().slice(11, 19) + "Z" : "—"}
              </span>
              <span className="text-[12px] text-fg-muted italic">
                {s.summary ?? "—"}
              </span>
            </li>
          );
        }
        const e = it.data;
        return (
          <li
            key={`event-${i}`}
            className="grid grid-cols-[24px_180px_72px_1fr] items-baseline gap-3 px-4 py-2 border-b border-border-subtle last:border-b-0"
          >
            <span className={`font-mono text-base ${CAMPAIGN_TONE[e.tone]}`}>
              {CAMPAIGN_ICON[e.tone]}
            </span>
            <span className="text-[12px] text-fg-default">{e.label}</span>
            <span className="font-mono text-[10px] text-fg-faint tabular-nums">
              {e.ts ? new Date(e.ts).toISOString().slice(11, 19) + "Z" : "—"}
            </span>
            <span className="text-[10px] text-fg-faint italic">
              {e.detail}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

function RawPanel({
  artifact,
  mission,
}: {
  artifact: Artifact | undefined;
  mission: Mission;
}) {
  let provenancePretty = "(none)";
  if (artifact) {
    try {
      provenancePretty = JSON.stringify(
        JSON.parse(artifact.finalProvenanceJson),
        null,
        2,
      );
    } catch {
      provenancePretty = artifact.finalProvenanceJson;
    }
  }
  let stagesPretty = "(none)";
  try {
    stagesPretty = JSON.stringify(JSON.parse(mission.stagesJson), null, 2);
  } catch {
    stagesPretty = mission.stagesJson;
  }
  return (
    <>
      <Block label="Provenance report (audit-source)">
        <pre className="text-[11px] overflow-x-auto text-fg-mono whitespace-pre">
          {provenancePretty}
        </pre>
      </Block>
      <Block label="Stages JSON">
        <pre className="text-[11px] overflow-x-auto text-fg-mono whitespace-pre">
          {stagesPretty}
        </pre>
      </Block>
    </>
  );
}

/* ─────────────────────────────────────────────────────────────────────── */
/* Atoms                                                                     */
/* ─────────────────────────────────────────────────────────────────────── */

function ArtifactVariantSwitcher({
  missionId,
  current,
}: {
  missionId: string;
  current: ArtifactVariant;
}) {
  const variants: ArtifactVariant[] = ["source", "stripped", "clean"];
  return (
    <div className="flex">
      {variants.map((v, i) => {
        const isActive = v === current;
        return (
          <Link
            key={v}
            href={{ pathname: "/", query: { m: missionId, v } }}
            scroll={false}
            replace
            prefetch={false}
            className={`px-2 py-[2px] font-mono text-[10px] uppercase tracking-[0.14em] border ${
              i > 0 ? "border-l-0" : ""
            } ${
              isActive
                ? "border-info-border bg-info-bg text-info-fg"
                : "border-border-default text-fg-muted hover:bg-bg-hover"
            }`}
          >
            {v}
          </Link>
        );
      })}
    </div>
  );
}

function MiniStat({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string | number;
  tone?: "default" | "info" | "pass" | "warn" | "fail";
}) {
  const valueColor =
    tone === "info"
      ? "text-info-fg"
      : tone === "pass"
        ? "text-pass-fg"
        : tone === "warn"
          ? "text-warn-fg"
          : tone === "fail"
            ? "text-fail-fg"
            : "text-fg-default";
  return (
    <div className="border border-border-subtle bg-bg-panel px-3 py-1 flex flex-col justify-center">
      <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-fg-faint">
        {label}
      </div>
      <div className={`text-[14px] font-medium tabular-nums ${valueColor}`}>
        {value}
      </div>
    </div>
  );
}

function summarizeArtifact(a: Artifact): string {
  if (a.passedC2pa && a.passedTitan && a.passedSynthid) {
    return `${a.artifactId} would not be flagged by any of the three provenance layers.`;
  }
  if (a.passedAll) return `${a.artifactId} passes the configured provenance bar.`;
  return `${a.artifactId} is flagged by at least one provenance check.`;
}

function formatRelative(iso: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toISOString().replace("T", " ").slice(0, 19) + "Z";
  } catch {
    return iso;
  }
}
