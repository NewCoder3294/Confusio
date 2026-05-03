import Link from "next/link";
import {
  getDashboardSnapshot,
  parseStages,
  type Mission,
  type Channel,
  type Artifact,
  type DetectionResult,
} from "@/lib/foundry";
import { StatusPill } from "@/components/status-pill";
import { DetectorPill } from "@/components/detector-pill";
import { StatTile } from "@/components/stat-tile";
import { StageTimeline } from "@/components/stage-timeline";

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

  const snap = await getDashboardSnapshot();
  const selected =
    snap.missions.find((m) => m.missionId === selectedId) ?? snap.missions[0];

  const counts = computeCounts(snap.missions);

  return (
    <div className="flex-1 flex flex-col">
      <section className="border-b border-border-subtle bg-bg-base">
        <div className="max-w-[1400px] mx-auto px-6 py-4 grid grid-cols-3 gap-3">
          <StatTile
            label="Active missions"
            value={counts.active}
            tone={counts.active > 0 ? "info" : "default"}
            hint="Status: executing"
          />
          <StatTile
            label="Completed missions"
            value={counts.completed}
            hint="Last 24h on this console"
          />
          <StatTile
            label="Recent pass rate"
            value={
              counts.recentPassRate === null
                ? "—"
                : `${Math.round(counts.recentPassRate * 100)}%`
            }
            tone={
              counts.recentPassRate !== null && counts.recentPassRate >= 0.8
                ? "info"
                : "warn"
            }
            hint="Avg of last 5 completed"
          />
        </div>
      </section>

      <section className="flex-1 grid grid-cols-[420px_1fr] min-h-0">
        <MissionList
          missions={snap.missions}
          selectedId={selected?.missionId}
          channelById={snap.channelById}
        />
        {selected ? (
          <MissionDetail
            mission={selected}
            channel={snap.channelById.get(selected.targetChannelId)}
            artifact={snap.artifactByMission.get(selected.missionId)}
            detections={
              snap.artifactByMission.get(selected.missionId)
                ? snap.detectionsByArtifact.get(
                    snap.artifactByMission.get(selected.missionId)!.artifactId
                  ) ?? []
                : []
            }
            variant={variant}
          />
        ) : (
          <EmptyDetail />
        )}
      </section>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────── */

function computeCounts(missions: Mission[]) {
  const now = Date.now();
  const active = missions.filter((m) => m.status === "executing").length;
  const dayAgo = now - 24 * 60 * 60 * 1000;
  const completedRecent = missions.filter(
    (m) =>
      m.status === "completed" &&
      m.finishedAt &&
      Date.parse(m.finishedAt) >= dayAgo
  );
  const completed = completedRecent.length;
  const lastFive = missions
    .filter((m) => m.status === "completed" && m.provenancePassRate !== null)
    .slice(0, 5);
  const recentPassRate =
    lastFive.length === 0
      ? null
      : lastFive.reduce((acc, m) => acc + (m.provenancePassRate ?? 0), 0) /
        lastFive.length;
  return { active, completed, recentPassRate };
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
  return (
    <aside className="border-r border-border-subtle bg-bg-panel overflow-y-auto">
      <div className="px-4 py-3 border-b border-border-subtle">
        <h2 className="text-[11px] font-mono uppercase tracking-[0.18em] text-fg-faint">
          Missions ({missions.length})
        </h2>
      </div>
      <ol>
        {missions.map((m) => {
          const channel = channelById.get(m.targetChannelId);
          const isSelected = m.missionId === selectedId;
          return (
            <li key={m.missionId}>
              <Link
                href={{ pathname: "/", query: { m: m.missionId } }}
                scroll={false}
                className={`block px-4 py-3 border-b border-border-subtle hover:bg-bg-hover transition-colors ${
                  isSelected
                    ? "bg-bg-elevated border-l-2 border-l-info-fg"
                    : "border-l-2 border-l-transparent"
                }`}
              >
                <div className="flex items-baseline justify-between gap-3">
                  <span className="font-mono text-[12px] text-fg-default">
                    {m.missionId}
                  </span>
                  <StatusPill status={m.status} />
                </div>
                <div className="mt-1 text-[11px] text-fg-muted truncate">
                  {channel?.displayName ?? m.targetChannelId}
                </div>
                <div className="mt-[2px] text-[10px] text-fg-faint truncate font-mono">
                  {formatRelative(m.createdAt)}
                </div>
              </Link>
            </li>
          );
        })}
      </ol>
    </aside>
  );
}

function EmptyDetail() {
  return (
    <div className="flex items-center justify-center text-fg-faint">
      <p className="italic">Select a mission from the list to view its record.</p>
    </div>
  );
}

function MissionDetail({
  mission,
  channel,
  artifact,
  detections,
  variant,
}: {
  mission: Mission;
  channel: Channel | undefined;
  artifact: Artifact | undefined;
  detections: DetectionResult[];
  variant: ArtifactVariant;
}) {
  const stages = parseStages(mission.stagesJson);

  return (
    <article className="overflow-y-auto">
      <header className="border-b border-border-subtle bg-bg-panel px-6 py-4">
        <div className="flex items-baseline justify-between gap-4">
          <div className="flex items-baseline gap-3">
            <h1 className="font-mono text-lg text-fg-default tracking-wide">
              {mission.missionId}
            </h1>
            <StatusPill status={mission.status} size="md" />
            {mission.dryRun && (
              <span className="font-mono text-[10px] tracking-[0.16em] text-fg-faint border border-border-default px-2 py-[1px]">
                DRY RUN
              </span>
            )}
          </div>
          <span className="font-mono text-[10px] text-fg-faint">
            {mission.dispatchedAt ? `dispatched ${mission.dispatchedAt}` : ""}
          </span>
        </div>
        <dl className="mt-3 grid grid-cols-[120px_1fr] gap-x-4 gap-y-1 text-[12px]">
          <Field label="Operator" value={mission.operator} mono />
          <Field
            label="Target"
            value={`${channel?.displayName ?? mission.targetChannelId} — ${
              mission.audienceProfile ||
              channel?.audienceProfile ||
              "(no profile)"
            }`}
          />
          <Field
            label="Persona"
            value={
              mission.personaArchetype
                ? `${mission.personaArchetype} (${mission.personaNameSeed || "—"})`
                : "—"
            }
          />
          <Field
            label="Created"
            value={`${mission.createdAt}${
              mission.finishedAt ? ` → ${mission.finishedAt}` : ""
            }`}
            mono
          />
        </dl>
      </header>

      <div className="max-w-[1100px] mx-auto px-6 py-6 flex flex-col gap-6">
        {artifact && (
          <Section title="Operator brief">
            <p className="text-[13px] leading-6 text-fg-default">
              {summarizeArtifact(artifact)}
            </p>
          </Section>
        )}

        {detections.length > 0 && (
          <Section title="Provenance grade">
            <div className="grid grid-cols-3 gap-2">
              {detections.map((d) => (
                <DetectorPill key={d.resultId} d={d} />
              ))}
            </div>
            <p className="mt-2 text-[10px] text-fg-faint font-mono uppercase tracking-[0.14em]">
              Tool grades itself with the same instruments an adversary&apos;s
              vetting pipeline would deploy.
            </p>
          </Section>
        )}

        {artifact && (
          <Section
            title="Artifact"
            subtitle={`sha256:${artifact.finalSha256.slice(0, 16)}…`}
          >
            <ArtifactCard
              artifact={artifact}
              mission={mission}
              variant={variant}
            />
          </Section>
        )}

        <Section title="Audit timeline">
          <StageTimeline stages={stages} />
        </Section>

        {artifact && <ProvenanceDrawer json={artifact.finalProvenanceJson} />}

        {mission.status === "failed" && mission.failureCode && (
          <div className="border border-fail-border bg-fail-bg px-4 py-3 text-fail-fg text-[12px]">
            <div className="font-mono uppercase tracking-[0.14em] text-[10px] mb-1">
              Failure
            </div>
            <div className="font-mono text-[12px]">{mission.failureCode}</div>
          </div>
        )}
      </div>
    </article>
  );
}

function ArtifactCard({
  artifact,
  mission,
  variant,
}: {
  artifact: Artifact;
  mission: Mission;
  variant: "clean" | "source" | "stripped";
}) {
  const VARIANT_COPY: Record<typeof variant, { label: string; sub: string }> = {
    source: {
      label: "SOURCE",
      sub: "Generator output — synthid + maker watermarks intact",
    },
    stripped: {
      label: "STRIPPED",
      sub: "Watermarks removed, EXIF cleared",
    },
    clean: {
      label: "CLEAN",
      sub: "EXIF transplanted, persona-consistent, ships",
    },
  };
  const copy = VARIANT_COPY[variant];

  return (
    <div className="border border-border-subtle bg-bg-panel">
      <div className="aspect-video bg-bg-base flex items-center justify-center border-b border-border-subtle overflow-hidden">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={`/api/artifact/${encodeURIComponent(artifact.artifactId)}?variant=${variant}`}
          alt={`Mission ${mission.missionId} artifact (${variant})`}
          className="max-h-full max-w-full object-contain"
        />
      </div>
      <div className="px-3 py-2 border-b border-border-subtle flex items-baseline justify-between gap-3">
        <div>
          <div className="font-mono text-[10px] tracking-[0.16em] text-fg-default">
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
      <dl className="text-[11px] divide-y divide-border-subtle">
        <KV k="prompt" v={artifact.prompt} />
        <KV k="path" v={artifact.finalPath} mono />
        <KV k="sha-256" v={artifact.finalSha256} mono />
        <KV k="all detectors passed" v={artifact.passedAll ? "yes" : "no"} mono />
        <KV
          k="caption (operator language)"
          v={mission.audienceProfile || "—"}
        />
      </dl>
    </div>
  );
}

function ArtifactVariantSwitcher({
  missionId,
  current,
}: {
  missionId: string;
  current: "clean" | "source" | "stripped";
}) {
  const variants: Array<"source" | "stripped" | "clean"> = [
    "source",
    "stripped",
    "clean",
  ];
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

function KV({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <div className="grid grid-cols-[180px_1fr] gap-3 px-3 py-2">
      <dt className="text-fg-faint uppercase tracking-[0.14em] font-mono text-[10px]">
        {k}
      </dt>
      <dd className={`text-fg-muted ${mono ? "font-mono text-[11px]" : ""} truncate`}>
        {v}
      </dd>
    </div>
  );
}

function Section({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <div className="flex items-baseline justify-between mb-2">
        <h2 className="text-[11px] font-mono uppercase tracking-[0.18em] text-fg-faint">
          {title}
        </h2>
        {subtitle && (
          <span className="font-mono text-[10px] text-fg-faint/80">
            {subtitle}
          </span>
        )}
      </div>
      {children}
    </section>
  );
}

function Field({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <>
      <dt className="text-fg-faint uppercase tracking-[0.14em] font-mono text-[10px]">
        {label}
      </dt>
      <dd className={`text-fg-muted ${mono ? "font-mono" : ""}`}>{value}</dd>
    </>
  );
}

function ProvenanceDrawer({ json }: { json: string }) {
  let pretty = json;
  try {
    pretty = JSON.stringify(JSON.parse(json), null, 2);
  } catch {
    /* keep raw */
  }
  return (
    <details className="border border-border-subtle bg-bg-panel">
      <summary className="px-4 py-2 cursor-pointer text-[11px] font-mono uppercase tracking-[0.14em] text-fg-muted hover:text-fg-default hover:bg-bg-hover">
        Raw provenance report (audit-source)
      </summary>
      <pre className="px-4 py-3 text-[11px] overflow-x-auto text-fg-mono whitespace-pre">
        {pretty}
      </pre>
    </details>
  );
}

function summarizeArtifact(a: Artifact): string {
  const treatment =
    a.passedC2pa && a.passedTitan && a.passedSynthid
      ? "would not be flagged by any of the three provenance layers an adversary is likely to deploy"
      : a.passedAll
        ? "passes the configured provenance bar"
        : "is flagged by at least one configured provenance check";
  return `Artifact ${a.artifactId} ${treatment}. Suitable for delivery on the targeted channel; operator should still verify caption and posting cadence match the persona's prior behavior.`;
}

function formatRelative(iso: string): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toISOString().replace("T", " ").slice(0, 19) + "Z";
  } catch {
    return iso;
  }
}
