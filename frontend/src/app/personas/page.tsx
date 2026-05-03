import Link from "next/link";
import {
  listPersonas,
  getActivityById,
  type Persona,
  type PersonaActivity,
} from "@/lib/personas";

export const metadata = {
  title: "Mendacity — Personas",
};

const EMPTY_ACTIVITY: PersonaActivity = {
  postsByStatus: {},
  totalPosts: 0,
  lastGeneratedAt: null,
  campaigns: [],
};

export default async function PersonasPage({
  searchParams,
}: {
  searchParams: Promise<{ [k: string]: string | string[] | undefined }>;
}) {
  const sp = await searchParams;
  const selectedId = typeof sp.p === "string" ? sp.p : undefined;

  const [personas, activityById] = await Promise.all([
    listPersonas(),
    getActivityById(),
  ]);
  const selected =
    personas.find((p) => p.id === selectedId) ?? personas[0] ?? null;

  return (
    <div className="flex-1 flex flex-col">
      <section className="border-b border-border-subtle bg-bg-panel">
        <div className="max-w-[1400px] mx-auto px-6 py-5">
          <div className="font-mono text-[10px] tracking-[0.18em] text-classified uppercase">
            Persona Library
          </div>
          <h1 className="mt-1 text-2xl text-fg-default tracking-wide font-medium">
            Fabricated Personas
          </h1>
          <p className="mt-2 text-[13px] text-fg-muted leading-6 max-w-[820px]">
            Persona-bound agents used as the supporting cast for offensive
            missions. Each persona has a stable voice, geographic anchor,
            posting cadence, and an explicit graph of which other personas it
            knows. Backstop coordination uses the graph to dispatch corroborating
            posts from adjacent personas after a primary artifact lands.
          </p>
        </div>
      </section>

      {personas.length === 0 ? (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-fg-faint italic">
            No personas configured. Drop JSON files in social/personas/.
          </p>
        </div>
      ) : (
        <section className="flex-1 grid grid-cols-[360px_1fr] min-h-0">
          <PersonaList
            personas={personas}
            activityById={activityById}
            selectedId={selected?.id}
          />
          {selected ? (
            <PersonaDetail
              persona={selected}
              activity={activityById.get(selected.id) ?? EMPTY_ACTIVITY}
              personasById={new Map(personas.map((p) => [p.id, p]))}
            />
          ) : null}
        </section>
      )}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────── */

function PersonaList({
  personas,
  activityById,
  selectedId,
}: {
  personas: Persona[];
  activityById: Map<string, PersonaActivity>;
  selectedId: string | undefined;
}) {
  return (
    <aside className="border-r border-border-subtle bg-bg-panel overflow-y-auto">
      <div className="px-4 py-3 border-b border-border-subtle">
        <h2 className="text-[11px] font-mono uppercase tracking-[0.18em] text-fg-faint">
          Roster ({personas.length})
        </h2>
      </div>
      <ol>
        {personas.map((p) => {
          const a = activityById.get(p.id) ?? EMPTY_ACTIVITY;
          const isSelected = p.id === selectedId;
          const dormant = a.totalPosts === 0;
          return (
            <li key={p.id}>
              <Link
                href={{ pathname: "/personas", query: { p: p.id } }}
                scroll={false}
                className={`block px-4 py-3 border-b border-border-subtle hover:bg-bg-hover transition-colors ${
                  isSelected
                    ? "bg-bg-elevated border-l-2 border-l-info-fg"
                    : "border-l-2 border-l-transparent"
                }`}
              >
                <div className="flex items-baseline justify-between gap-3">
                  <span className="text-[13px] text-fg-default">{p.name}</span>
                  <span className="font-mono text-[10px] text-fg-faint uppercase tracking-[0.14em]">
                    {p.language || "—"}
                  </span>
                </div>
                <div className="mt-1 text-[11px] text-fg-muted truncate">
                  {p.geoAnchor || "—"}
                </div>
                <div className="mt-[2px] text-[10px] text-fg-faint truncate font-mono">
                  {dormant
                    ? "no operational history"
                    : `${a.totalPosts} post${a.totalPosts === 1 ? "" : "s"} across ${a.campaigns.length} campaign${a.campaigns.length === 1 ? "" : "s"}`}
                </div>
              </Link>
            </li>
          );
        })}
      </ol>
    </aside>
  );
}

function PersonaDetail({
  persona,
  activity,
  personasById,
}: {
  persona: Persona;
  activity: PersonaActivity;
  personasById: Map<string, Persona>;
}) {
  return (
    <article className="overflow-y-auto">
      <header className="border-b border-border-subtle bg-bg-panel px-6 py-4">
        <div className="flex items-baseline justify-between gap-4">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-fg-faint">
              {persona.id}
            </div>
            <h1 className="mt-1 text-xl text-fg-default tracking-wide font-medium">
              {persona.name}
            </h1>
          </div>
          <CadencePill schedule={persona.postingSchedule} />
        </div>
        <dl className="mt-3 grid grid-cols-[140px_1fr] gap-x-4 gap-y-1 text-[12px]">
          <Field label="Language" value={persona.language || "—"} mono />
          <Field label="Geo anchor" value={persona.geoAnchor || "—"} />
          <Field label="Bio" value={persona.bioShort || "—"} />
          <Field
            label="Session"
            value={persona.sessionPath || "—"}
            mono
          />
        </dl>
      </header>

      <div className="max-w-[1100px] mx-auto px-6 py-6 flex flex-col gap-6">
        <Section title="Operational history">
          <div className="grid grid-cols-4 gap-2">
            <Tally label="Total posts" value={activity.totalPosts} />
            <Tally
              label="Posted"
              value={activity.postsByStatus.posted ?? 0}
              tone="pass"
            />
            <Tally
              label="Pending approval"
              value={activity.postsByStatus.pending_approval ?? 0}
              tone="warn"
            />
            <Tally
              label="Last generated"
              value={
                activity.lastGeneratedAt
                  ? formatRelative(activity.lastGeneratedAt)
                  : "—"
              }
              small
            />
          </div>
        </Section>

        {activity.campaigns.length > 0 && (
          <Section title="Recent campaigns">
            <div className="border border-border-subtle bg-bg-panel">
              <table className="w-full text-[12px]">
                <thead>
                  <tr className="border-b border-border-subtle text-[10px] uppercase tracking-[0.14em] text-fg-faint font-mono">
                    <th className="text-left px-3 py-2 font-medium">Created</th>
                    <th className="text-left px-3 py-2 font-medium">Intent</th>
                    <th className="text-left px-3 py-2 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {activity.campaigns.map((c) => (
                    <tr
                      key={c.id}
                      className="border-b border-border-subtle last:border-b-0"
                    >
                      <td className="px-3 py-2 font-mono text-fg-mono whitespace-nowrap">
                        {formatRelative(c.createdAt)}
                      </td>
                      <td className="px-3 py-2 text-fg-muted">
                        {c.intent}
                      </td>
                      <td className="px-3 py-2 font-mono text-[11px] text-fg-default uppercase tracking-[0.14em]">
                        {c.status}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>
        )}

        <Section title="Voice profile">
          <div className="border border-border-subtle bg-bg-panel">
            <dl className="text-[12px] divide-y divide-border-subtle">
              <Block label="Backstory" value={persona.backstory} />
              <Block label="Style" value={persona.style} />
              {persona.vocabularyQuirks.length > 0 && (
                <Tags label="Vocabulary quirks" items={persona.vocabularyQuirks} />
              )}
              {persona.topicFocus.length > 0 && (
                <Tags label="Topic focus" items={persona.topicFocus} />
              )}
            </dl>
          </div>
        </Section>

        {persona.examples.length > 0 && (
          <Section title="Sample posts">
            <ol className="border border-border-subtle bg-bg-panel divide-y divide-border-subtle">
              {persona.examples.map((ex, i) => (
                <li
                  key={i}
                  className="px-4 py-3 flex gap-3 text-[12px] leading-6"
                >
                  <span className="font-mono text-[10px] text-fg-faint w-6 tabular-nums shrink-0">
                    {String(i + 1).padStart(2, "0")}.
                  </span>
                  <span className="text-fg-default italic">&ldquo;{ex}&rdquo;</span>
                </li>
              ))}
            </ol>
          </Section>
        )}

        <Section title="Persona graph — corroboration network">
          {persona.knows.length === 0 ? (
            <p className="text-[12px] text-fg-faint italic">
              {persona.name} operates alone. No corroborating personas declared.
            </p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {persona.knows.map((kid) => {
                const k = personasById.get(kid);
                return (
                  <Link
                    key={kid}
                    href={{ pathname: "/personas", query: { p: kid } }}
                    className="border border-border-default bg-bg-panel hover:bg-bg-hover px-3 py-2 flex flex-col gap-[2px]"
                  >
                    <span className="font-mono text-[10px] tracking-[0.14em] text-fg-faint uppercase">
                      Knows
                    </span>
                    <span className="text-[13px] text-fg-default">
                      {k?.name ?? kid}
                    </span>
                    {k?.geoAnchor && (
                      <span className="text-[10px] text-fg-faint italic">
                        {k.geoAnchor}
                      </span>
                    )}
                  </Link>
                );
              })}
            </div>
          )}
          <p className="mt-2 text-[10px] text-fg-faint font-mono uppercase tracking-[0.14em]">
            Backstop coordination dispatches corroborating posts from these
            personas after a primary artifact lands.
          </p>
        </Section>
      </div>
    </article>
  );
}

function CadencePill({
  schedule,
}: {
  schedule: Persona["postingSchedule"];
}) {
  const [start, end] = schedule.activeHoursLocal;
  return (
    <div className="border border-border-default bg-bg-elevated px-3 py-2 text-right">
      <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-fg-faint">
        Cadence
      </div>
      <div className="font-mono text-[12px] text-fg-default mt-[2px]">
        {schedule.avgPostsPerDay}/day · {String(start).padStart(2, "0")}–
        {String(end).padStart(2, "0")} local
      </div>
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <h2 className="text-[11px] font-mono uppercase tracking-[0.18em] text-fg-faint mb-2">
        {title}
      </h2>
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

function Tally({
  label,
  value,
  tone = "default",
  small = false,
}: {
  label: string;
  value: string | number;
  tone?: "default" | "pass" | "warn";
  small?: boolean;
}) {
  const valueColor =
    tone === "pass"
      ? "text-pass-fg"
      : tone === "warn"
        ? "text-warn-fg"
        : "text-fg-default";
  return (
    <div className="border border-border-subtle bg-bg-panel px-4 py-3">
      <div className="text-[10px] uppercase tracking-[0.16em] text-fg-faint font-mono">
        {label}
      </div>
      <div
        className={`mt-1 font-medium tabular-nums ${valueColor} ${small ? "text-[13px] font-mono" : "text-2xl"}`}
      >
        {value}
      </div>
    </div>
  );
}

function Block({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[140px_1fr] gap-3 px-3 py-2">
      <dt className="text-fg-faint uppercase tracking-[0.14em] font-mono text-[10px]">
        {label}
      </dt>
      <dd className="text-fg-default leading-6">{value}</dd>
    </div>
  );
}

function Tags({ label, items }: { label: string; items: string[] }) {
  return (
    <div className="grid grid-cols-[140px_1fr] gap-3 px-3 py-2">
      <dt className="text-fg-faint uppercase tracking-[0.14em] font-mono text-[10px]">
        {label}
      </dt>
      <dd className="flex flex-wrap gap-1">
        {items.map((t, i) => (
          <span
            key={i}
            className="inline-block border border-border-default bg-bg-base px-2 py-[2px] text-[11px] text-fg-mono font-mono"
          >
            {t}
          </span>
        ))}
      </dd>
    </div>
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
