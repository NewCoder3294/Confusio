import Link from "next/link";
import {
  effectiveStatus,
  type Campaign,
  type GeneratedPost,
} from "@/lib/campaigns";
import { type Persona } from "@/lib/personas";
import { Block } from "@/components/surfaces";

// Re-export the live, metadata-driven Injection panel so existing call sites
// (Mission Board MissionDetail) get the new behavior without import churn.
export { InjectionPanel } from "@/components/injection-panel";

/* ─────────────────────────────────────────────────────────────────────── */
/* Cast — operator-assigned roster + recommended corroborators             */
/* ─────────────────────────────────────────────────────────────────────── */

export function CastPanel({
  campaign,
  personasById,
}: {
  campaign: Campaign;
  personasById: Map<string, Persona>;
}) {
  const seedIds = Object.entries(campaign.roster)
    .filter(([, role]) => role === "seed")
    .map(([id]) => id);
  const inferred = inferCorroborators(seedIds, campaign.roster, personasById);

  return (
    <>
      <Block label="Operator-assigned">
        {Object.keys(campaign.roster).length === 0 ? (
          <p className="text-[12px] text-fg-faint italic">
            No personas assigned.
          </p>
        ) : (
          <div className="grid grid-cols-2 gap-2">
            {Object.entries(campaign.roster).map(([pid, role]) => (
              <RosterCard
                key={pid}
                persona={personasById.get(pid)}
                pid={pid}
                role={role}
                inferred={false}
              />
            ))}
          </div>
        )}
      </Block>
      {inferred.length > 0 && (
        <Block label="Recommended corroborators — from persona graph">
          <div className="grid grid-cols-2 gap-2">
            {inferred.map(({ persona, viaPersonaId }) => (
              <RosterCard
                key={persona.id}
                persona={persona}
                pid={persona.id}
                role="corroborator"
                inferred
                via={personasById.get(viaPersonaId)?.name ?? viaPersonaId}
              />
            ))}
          </div>
        </Block>
      )}
    </>
  );
}

function inferCorroborators(
  seedIds: string[],
  currentRoster: Record<string, string>,
  personasById: Map<string, Persona>,
): Array<{ persona: Persona; viaPersonaId: string }> {
  const out: Array<{ persona: Persona; viaPersonaId: string }> = [];
  const seen = new Set(Object.keys(currentRoster));
  for (const seedId of seedIds) {
    const seed = personasById.get(seedId);
    if (!seed) continue;
    for (const knowsId of seed.knows) {
      if (seen.has(knowsId)) continue;
      const k = personasById.get(knowsId);
      if (!k) continue;
      out.push({ persona: k, viaPersonaId: seedId });
      seen.add(knowsId);
    }
  }
  return out;
}

function RosterCard({
  persona,
  pid,
  role,
  inferred,
  via,
}: {
  persona: Persona | undefined;
  pid: string;
  role: string;
  inferred: boolean;
  via?: string;
}) {
  const tone = inferred
    ? "border-info-border bg-info-bg/30"
    : role === "seed"
      ? "border-pass-border bg-pass-bg/40"
      : "border-border-default bg-bg-panel";
  return (
    <Link
      href={{ pathname: "/personas", query: { p: pid } }}
      className={`border ${tone} px-3 py-2 hover:bg-bg-hover transition-colors`}
    >
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-[12px] text-fg-default">
          {persona?.name ?? pid}
        </span>
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-fg-faint">
          {role}
        </span>
      </div>
      <div className="mt-[2px] text-[10px] text-fg-muted truncate">
        {persona?.geoAnchor ?? "—"} · {persona?.language ?? "—"}
      </div>
      {inferred && via && (
        <div className="mt-1 text-[10px] text-fg-faint italic">via {via}</div>
      )}
    </Link>
  );
}

/* ─────────────────────────────────────────────────────────────────────── */
/* Posts                                                                    */
/* ─────────────────────────────────────────────────────────────────────── */

export function PostsPanel({
  posts,
  personasById,
}: {
  posts: GeneratedPost[];
  personasById: Map<string, Persona>;
}) {
  const now = Date.now();
  if (posts.length === 0) {
    return (
      <div className="px-4 py-6 text-fg-faint italic text-[12px]">
        No posts generated yet.
      </div>
    );
  }
  return (
    <ol>
      {posts.map((post) => {
        const persona = personasById.get(post.personaId);
        const content = post.editedContent || post.generatedContent;
        const eff = effectiveStatus(post, now);
        return (
          <li
            key={post.id}
            className="px-4 py-3 border-b border-border-subtle last:border-b-0 flex flex-col gap-2"
          >
            <div className="flex items-baseline justify-between gap-3">
              <div className="flex items-baseline gap-2">
                <span className="text-[12px] text-fg-default">
                  {persona?.name ?? post.personaId}
                </span>
                <span className="font-mono text-[10px] tracking-[0.14em] uppercase text-fg-faint">
                  {post.role}
                </span>
                <PostStatusPill status={eff} />
              </div>
              <span className="font-mono text-[10px] text-fg-faint tabular-nums">
                {fmtRelative(post.generatedAt)}
              </span>
            </div>
            <p className="text-[12px] text-fg-default leading-5 whitespace-pre-wrap font-mono">
              {content}
            </p>
            {post.error && (
              <p className="text-[11px] text-fail-fg font-mono">{post.error}</p>
            )}
          </li>
        );
      })}
    </ol>
  );
}

function PostStatusPill({ status }: { status: string }) {
  const TONE: Record<string, string> = {
    posted: "border-pass-border bg-pass-bg text-pass-fg",
    scheduled: "border-info-border bg-info-bg text-info-fg",
    pending_approval: "border-warn-border bg-warn-bg text-warn-fg",
    rejected: "border-fail-border bg-fail-bg text-fail-fg",
    error: "border-fail-border bg-fail-bg text-fail-fg",
  };
  const cls = TONE[status] ?? "border-border-default bg-neutral-bg text-neutral-fg";
  return (
    <span
      className={`inline-block border font-mono font-medium uppercase px-2 py-[1px] text-[9px] tracking-[0.14em] ${cls}`}
    >
      {status.replace(/_/g, " ")}
    </span>
  );
}

/* ─────────────────────────────────────────────────────────────────────── */
/* Campaign-side timeline events (post drafted/delivered) — combined into  */
/* the Mission Board's Timeline tab alongside Foundry stage events.        */
/* ─────────────────────────────────────────────────────────────────────── */

export type TimelineEvent = {
  ts: string;
  label: string;
  detail: string;
  tone: "info" | "pass" | "warn" | "fail" | "neutral";
};

export function buildCampaignEvents(
  campaign: Campaign,
  posts: GeneratedPost[],
  personasById: Map<string, Persona>,
): TimelineEvent[] {
  const now = Date.now();
  const events: TimelineEvent[] = [];
  events.push({
    ts: campaign.createdAt,
    label: "Campaign opened",
    detail: campaign.createdBy,
    tone: "info",
  });
  for (const post of posts) {
    const personaName = personasById.get(post.personaId)?.name ?? post.personaId;
    const eff = effectiveStatus(post, now);
    events.push({
      ts: post.generatedAt,
      label: `${personaName} drafted`,
      detail: post.role,
      tone: "neutral",
    });
    if (post.postedAt) {
      const future = eff === "scheduled";
      events.push({
        ts: post.postedAt,
        label: `${personaName} ${future ? "scheduled to post" : "delivered"}`,
        detail: post.telegramMessageId
          ? `tg ${post.telegramMessageId}`
          : future
            ? `in ${Math.max(0, Math.round((Date.parse(post.postedAt) - now) / 1000))}s`
            : "",
        tone: future ? "warn" : "pass",
      });
    }
  }
  return events.sort((a, b) => a.ts.localeCompare(b.ts));
}

function fmtRelative(iso: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toISOString().replace("T", " ").slice(0, 19) + "Z";
  } catch {
    return iso;
  }
}
