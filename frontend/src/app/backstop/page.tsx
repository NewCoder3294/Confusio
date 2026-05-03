import Link from "next/link";
import {
  listCampaigns,
  listAllPosts,
  type Campaign,
  type GeneratedPost,
} from "@/lib/campaigns";
import { listPersonas, type Persona } from "@/lib/personas";

export const metadata = {
  title: "Mendacity — Backstop Operations",
};

export default async function BackstopPage({
  searchParams,
}: {
  searchParams: Promise<{ [k: string]: string | string[] | undefined }>;
}) {
  const sp = await searchParams;
  const selectedId = typeof sp.c === "string" ? sp.c : undefined;

  const [campaigns, allPosts, personas] = await Promise.all([
    listCampaigns(),
    listAllPosts(),
    listPersonas(),
  ]);

  const personasById = new Map(personas.map((p) => [p.id, p]));
  const postsByCampaign = new Map<string, GeneratedPost[]>();
  for (const post of allPosts) {
    const arr = postsByCampaign.get(post.campaignId) ?? [];
    arr.push(post);
    postsByCampaign.set(post.campaignId, arr);
  }

  const selected =
    campaigns.find((c) => c.id === selectedId) ?? campaigns[0] ?? null;

  return (
    <div className="flex-1 flex flex-col">
      <section className="border-b border-border-subtle bg-bg-panel">
        <div className="max-w-[1400px] mx-auto px-6 py-5">
          <div className="font-mono text-[10px] tracking-[0.18em] text-classified uppercase">
            Offensive — Coordinated Narrative Dispatch
          </div>
          <h1 className="mt-1 text-2xl text-fg-default tracking-wide font-medium">
            Backstop Operations
          </h1>
          <p className="mt-2 text-[13px] text-fg-muted leading-6 max-w-[820px]">
            A planted artifact lands inside a coordinated narrative, never
            alone. Backstop dispatches corroborating posts from adjacent
            personas in the operator&apos;s graph — eyewitness echoes, news-style
            aggregation, sardonic cross-references — staggered to mimic
            organic uptake. Each post requires explicit operator approval
            before transmission.
          </p>
        </div>
      </section>

      {campaigns.length === 0 ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center px-8 py-12 max-w-md">
            <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-fg-faint">
              No backstop campaigns recorded
            </div>
            <p className="mt-3 text-[13px] text-fg-muted leading-6">
              Once the operator dispatches a campaign, the seed post and its
              persona-graph corroboration network will appear here. Source of
              truth: <span className="font-mono">social/mendacity.db</span>.
            </p>
          </div>
        </div>
      ) : (
        <section className="flex-1 grid grid-cols-[420px_1fr] min-h-0">
          <CampaignList
            campaigns={campaigns}
            postsByCampaign={postsByCampaign}
            selectedId={selected?.id}
          />
          {selected && (
            <CampaignDetail
              campaign={selected}
              posts={postsByCampaign.get(selected.id) ?? []}
              personasById={personasById}
            />
          )}
        </section>
      )}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────── */

function CampaignList({
  campaigns,
  postsByCampaign,
  selectedId,
}: {
  campaigns: Campaign[];
  postsByCampaign: Map<string, GeneratedPost[]>;
  selectedId: string | undefined;
}) {
  return (
    <aside className="border-r border-border-subtle bg-bg-panel overflow-y-auto">
      <div className="px-4 py-3 border-b border-border-subtle">
        <h2 className="text-[11px] font-mono uppercase tracking-[0.18em] text-fg-faint">
          Campaigns ({campaigns.length})
        </h2>
      </div>
      <ol>
        {campaigns.map((c) => {
          const posts = postsByCampaign.get(c.id) ?? [];
          const isSelected = c.id === selectedId;
          const rosterSize = Object.keys(c.roster).length;
          return (
            <li key={c.id}>
              <Link
                href={{ pathname: "/backstop", query: { c: c.id } }}
                scroll={false}
                className={`block px-4 py-3 border-b border-border-subtle hover:bg-bg-hover transition-colors ${
                  isSelected
                    ? "bg-bg-elevated border-l-2 border-l-info-fg"
                    : "border-l-2 border-l-transparent"
                }`}
              >
                <div className="flex items-baseline justify-between gap-3">
                  <span className="font-mono text-[11px] text-fg-default truncate">
                    {c.id}
                  </span>
                  <CampaignStatusPill status={c.status} />
                </div>
                <div className="mt-1 text-[12px] text-fg-default leading-5 line-clamp-2">
                  {c.intent}
                </div>
                <div className="mt-[2px] text-[10px] text-fg-faint truncate font-mono">
                  {rosterSize} persona{rosterSize === 1 ? "" : "s"} ·{" "}
                  {posts.length} post{posts.length === 1 ? "" : "s"} ·{" "}
                  {formatRelative(c.createdAt)}
                </div>
              </Link>
            </li>
          );
        })}
      </ol>
    </aside>
  );
}

function CampaignDetail({
  campaign,
  posts,
  personasById,
}: {
  campaign: Campaign;
  posts: GeneratedPost[];
  personasById: Map<string, Persona>;
}) {
  const seedPersonaIds = Object.entries(campaign.roster)
    .filter(([, role]) => role === "seed")
    .map(([id]) => id);
  const inferredCorroborators = inferCorroborators(
    seedPersonaIds,
    campaign.roster,
    personasById,
  );

  const [delayMin, delayMax] = campaign.delayRangeSeconds;

  return (
    <article className="overflow-y-auto">
      <header className="border-b border-border-subtle bg-bg-panel px-6 py-4">
        <div className="flex items-baseline justify-between gap-4">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-fg-faint">
              {campaign.id}
            </div>
            <h1 className="mt-1 text-lg text-fg-default leading-6 max-w-[700px]">
              {campaign.intent}
            </h1>
          </div>
          <CampaignStatusPill status={campaign.status} size="md" />
        </div>
        <dl className="mt-3 grid grid-cols-[140px_1fr] gap-x-4 gap-y-1 text-[12px]">
          <Field label="Channel" value={campaign.channel} mono />
          <Field label="Operator" value={campaign.createdBy} mono />
          <Field label="Created" value={campaign.createdAt} mono />
          <Field
            label="Stagger"
            value={`${delayMin}–${delayMax}s between posts`}
            mono
          />
        </dl>
      </header>

      <div className="max-w-[1100px] mx-auto px-6 py-6 flex flex-col gap-6">
        <Section title="Roster — operator-assigned">
          {Object.keys(campaign.roster).length === 0 ? (
            <p className="text-[12px] text-fg-faint italic">
              No personas assigned. Campaign is not actionable.
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
        </Section>

        {inferredCorroborators.length > 0 && (
          <Section
            title="Persona-graph corroborators — recommended add"
            subtitle="Inferred from 'knows' edges; not yet scheduled"
          >
            <div className="grid grid-cols-2 gap-2">
              {inferredCorroborators.map(({ persona, viaPersonaId }) => (
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
          </Section>
        )}

        <Section title="Dispatch timeline">
          <DispatchTimeline
            campaign={campaign}
            posts={posts}
            personasById={personasById}
          />
        </Section>

        {posts.length > 0 && (
          <Section title="Generated posts">
            <ol className="border border-border-subtle bg-bg-panel divide-y divide-border-subtle">
              {posts.map((post) => (
                <PostRow
                  key={post.id}
                  post={post}
                  persona={personasById.get(post.personaId)}
                />
              ))}
            </ol>
          </Section>
        )}
      </div>
    </article>
  );
}

function inferCorroborators(
  seedPersonaIds: string[],
  currentRoster: Record<string, string>,
  personasById: Map<string, Persona>,
): Array<{ persona: Persona; viaPersonaId: string }> {
  const out: Array<{ persona: Persona; viaPersonaId: string }> = [];
  const seen = new Set(Object.keys(currentRoster));
  for (const seedId of seedPersonaIds) {
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
        <span className="text-[13px] text-fg-default">
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
        <div className="mt-1 text-[10px] text-fg-faint italic">
          via {via}&apos;s graph
        </div>
      )}
    </Link>
  );
}

function DispatchTimeline({
  campaign,
  posts,
  personasById,
}: {
  campaign: Campaign;
  posts: GeneratedPost[];
  personasById: Map<string, Persona>;
}) {
  // Build an event list: campaign created → each post generated → each post posted.
  type Event = {
    ts: string;
    label: string;
    detail: string;
    tone: "info" | "pass" | "warn" | "fail" | "neutral";
  };
  const events: Event[] = [];
  events.push({
    ts: campaign.createdAt,
    label: "Campaign opened",
    detail: `Operator: ${campaign.createdBy}`,
    tone: "info",
  });
  for (const post of posts) {
    const personaName = personasById.get(post.personaId)?.name ?? post.personaId;
    events.push({
      ts: post.generatedAt,
      label: `${personaName} drafted`,
      detail: `Role: ${post.role}`,
      tone: "neutral",
    });
    if (post.decidedAt) {
      events.push({
        ts: post.decidedAt,
        label: `${personaName} ${post.status === "rejected" ? "rejected" : "approved"}`,
        detail: post.decidedBy ? `By ${post.decidedBy}` : "",
        tone: post.status === "rejected" ? "fail" : "pass",
      });
    }
    if (post.postedAt) {
      events.push({
        ts: post.postedAt,
        label: `${personaName} delivered`,
        detail: post.telegramMessageId
          ? `tg msg ${post.telegramMessageId}`
          : "Telegram",
        tone: "pass",
      });
    }
  }
  events.sort((a, b) => a.ts.localeCompare(b.ts));

  if (events.length === 0) {
    return (
      <p className="text-[12px] text-fg-faint italic">
        No dispatch events yet for this campaign.
      </p>
    );
  }
  const TONE: Record<Event["tone"], string> = {
    info: "text-info-fg",
    pass: "text-pass-fg",
    warn: "text-warn-fg",
    fail: "text-fail-fg",
    neutral: "text-fg-muted",
  };
  const ICON: Record<Event["tone"], string> = {
    info: "→",
    pass: "✓",
    warn: "·",
    fail: "✗",
    neutral: "·",
  };
  return (
    <ol className="border border-border-subtle bg-bg-panel divide-y divide-border-subtle">
      {events.map((e, i) => (
        <li
          key={i}
          className="grid grid-cols-[24px_180px_1fr_auto] items-baseline gap-3 px-4 py-2"
        >
          <span className={`font-mono text-base ${TONE[e.tone]}`}>
            {ICON[e.tone]}
          </span>
          <span className="font-mono text-[11px] text-fg-mono tabular-nums">
            {formatRelative(e.ts)}
          </span>
          <span className="text-[12px] text-fg-default">{e.label}</span>
          <span className="text-[11px] text-fg-faint italic">{e.detail}</span>
        </li>
      ))}
    </ol>
  );
}

function PostRow({
  post,
  persona,
}: {
  post: GeneratedPost;
  persona: Persona | undefined;
}) {
  const content = post.editedContent || post.generatedContent;
  return (
    <li className="px-4 py-3 flex flex-col gap-2">
      <div className="flex items-baseline justify-between gap-3">
        <div className="flex items-baseline gap-3">
          <span className="text-[13px] text-fg-default">
            {persona?.name ?? post.personaId}
          </span>
          <span className="font-mono text-[10px] tracking-[0.14em] uppercase text-fg-faint">
            {post.role}
          </span>
          <PostStatusPill status={post.status} />
        </div>
        <span className="font-mono text-[10px] text-fg-faint tabular-nums">
          {formatRelative(post.generatedAt)}
        </span>
      </div>
      <p className="text-[12px] text-fg-default leading-5 whitespace-pre-wrap font-mono">
        {content}
      </p>
      {post.error && (
        <p className="text-[11px] text-fail-fg font-mono">Error: {post.error}</p>
      )}
    </li>
  );
}

function PostStatusPill({ status }: { status: string }) {
  const TONE: Record<string, string> = {
    posted: "border-pass-border bg-pass-bg text-pass-fg",
    pending_approval: "border-warn-border bg-warn-bg text-warn-fg",
    rejected: "border-fail-border bg-fail-bg text-fail-fg",
    error: "border-fail-border bg-fail-bg text-fail-fg",
  };
  const cls = TONE[status] ?? "border-border-default bg-neutral-bg text-neutral-fg";
  return (
    <span
      className={`inline-block border font-mono font-medium uppercase px-2 py-[2px] text-[10px] tracking-[0.14em] ${cls}`}
    >
      {status.replace(/_/g, " ")}
    </span>
  );
}

function CampaignStatusPill({
  status,
  size = "sm",
}: {
  status: string;
  size?: "sm" | "md";
}) {
  const TONE: Record<string, string> = {
    running: "border-info-border bg-info-bg text-info-fg",
    completed: "border-pass-border bg-pass-bg text-pass-fg",
    aborted: "border-neutral-border bg-neutral-bg text-neutral-fg",
    draft: "border-border-default bg-bg-elevated text-fg-muted",
  };
  const cls = TONE[status] ?? "border-border-default bg-neutral-bg text-neutral-fg";
  const sizing =
    size === "md"
      ? "px-3 py-1 text-[11px] tracking-[0.16em]"
      : "px-2 py-[2px] text-[10px] tracking-[0.14em]";
  return (
    <span
      className={`inline-block border font-mono font-medium uppercase ${cls} ${sizing}`}
    >
      {status}
    </span>
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
          <span className="font-mono text-[10px] text-fg-faint/80 italic">
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
      <dd className={`text-fg-muted ${mono ? "font-mono" : ""} truncate`}>
        {value}
      </dd>
    </>
  );
}

function formatRelative(iso: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toISOString().replace("T", " ").slice(0, 19) + "Z";
  } catch {
    return iso;
  }
}
