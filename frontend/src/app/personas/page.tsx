import Link from "next/link";
import {
  listPersonas,
  getActivityById,
  type Persona,
  type PersonaActivity,
} from "@/lib/personas";
import { Card, Tabs, Block, Row, PageHeader } from "@/components/surfaces";
import { NewAgentTrigger } from "@/components/new-agent-trigger";
import { DeleteAgentButton } from "@/components/delete-agent-button";

export const metadata = {
  title: "Confusio — Agents",
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
  const personasById = new Map(personas.map((p) => [p.id, p]));
  const agentLite = personas.map((p) => ({
    id: p.id,
    name: p.name,
    language: p.language,
    geoAnchor: p.geoAnchor,
  }));

  return (
    <>
      <PageHeader
        eyebrow="Agent library"
        title="Fabricated Agents"
        brief="Stable identities used for the seed post and the corroborating cast that follows. Each agent has a voice profile and a graph of who it knows."
        actions={<NewAgentTrigger agents={agentLite} />}
      />

      <div className="flex-1 min-h-0 w-full mx-auto px-6 py-3 grid grid-cols-[280px_1fr] gap-3">
        <Card title="Roster" meta={`${personas.length}`}>
          <PersonaList
            personas={personas}
            activityById={activityById}
            selectedId={selected?.id}
          />
        </Card>

        {selected ? (
          <PersonaDetail
            persona={selected}
            activity={activityById.get(selected.id) ?? EMPTY_ACTIVITY}
            personasById={personasById}
          />
        ) : (
          <Card title="No agent selected">
            <div className="px-4 py-8 text-fg-faint italic text-[14px] text-center">
              Pick an agent from the left, or create one with{" "}
              <span className="font-mono">+ New agent</span>.
            </div>
          </Card>
        )}
      </div>
    </>
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
  if (personas.length === 0) {
    return (
      <div className="px-4 py-6 text-fg-faint italic text-[14px]">
        No agents configured.
      </div>
    );
  }
  return (
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
              className={`block px-3 py-2 border-b border-border-subtle hover:bg-bg-hover transition-colors ${
                isSelected
                  ? "bg-bg-elevated border-l-2 border-l-info-fg"
                  : "border-l-2 border-l-transparent"
              }`}
            >
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-[14px] text-fg-default truncate">
                  {p.name}
                </span>
                <span className="font-mono text-[11px] text-fg-faint uppercase tracking-[0.14em]">
                  {p.language || "—"}
                </span>
              </div>
              <div className="mt-[1px] text-[12px] text-fg-faint truncate font-mono">
                {p.geoAnchor || "—"} · {dormant ? "dormant" : `${a.totalPosts}p`}
              </div>
            </Link>
          </li>
        );
      })}
    </ol>
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
    <Card
      title={persona.name}
      meta={`${persona.id} · ${persona.language}`}
      actions={
        <DeleteAgentButton agentId={persona.id} agentName={persona.name} />
      }
    >
      <Tabs
        tabs={[
          {
            id: "profile",
            label: "Profile",
            panel: <ProfilePanel persona={persona} />,
          },
          {
            id: "activity",
            label: "Activity",
            count: activity.totalPosts,
            panel: <ActivityPanel activity={activity} />,
          },
          {
            id: "voice",
            label: "Voice",
            count: persona.examples.length,
            panel: <VoicePanel persona={persona} />,
          },
          {
            id: "network",
            label: "Network",
            count: persona.knows.length,
            panel: (
              <NetworkPanel persona={persona} personasById={personasById} />
            ),
          },
        ]}
      />
    </Card>
  );
}

function ProfilePanel({ persona }: { persona: Persona }) {
  const [start, end] = persona.postingSchedule.activeHoursLocal;
  return (
    <>
      <Block label="Identity">
        <dl>
          <Row label="Geo anchor" value={persona.geoAnchor || "—"} />
          <Row label="Language" value={persona.language || "—"} mono />
          <Row label="Bio" value={persona.bioShort || "—"} />
        </dl>
      </Block>
      <Block label="Cadence">
        <dl>
          <Row
            label="Posts per day"
            value={String(persona.postingSchedule.avgPostsPerDay)}
            mono
          />
          <Row
            label="Active hours"
            value={`${String(start).padStart(2, "0")}–${String(end).padStart(2, "0")} local`}
            mono
          />
        </dl>
      </Block>
      <Block label="Session">
        <dl>
          <Row label="Path" value={persona.sessionPath || "—"} mono />
        </dl>
      </Block>
    </>
  );
}

function ActivityPanel({ activity }: { activity: PersonaActivity }) {
  if (activity.totalPosts === 0) {
    return (
      <Block>
        <p className="text-[14px] text-fg-faint italic">
          No operational history yet.
        </p>
      </Block>
    );
  }
  return (
    <>
      <Block label="Counts">
        <div className="grid grid-cols-3 gap-2">
          <Stat label="Total" value={activity.totalPosts} />
          <Stat
            label="Posted"
            value={activity.postsByStatus.posted ?? 0}
            tone="pass"
          />
          <Stat
            label="Pending"
            value={activity.postsByStatus.pending_approval ?? 0}
            tone="warn"
          />
        </div>
        {activity.lastGeneratedAt && (
          <div className="mt-3 text-[12px] font-mono text-fg-faint uppercase tracking-[0.14em]">
            Last generated · {formatRelative(activity.lastGeneratedAt)}
          </div>
        )}
      </Block>
      {activity.campaigns.length > 0 && (
        <Block label="Recent campaigns">
          <table className="w-full text-[14px]">
            <thead>
              <tr className="border-b border-border-subtle text-[12px] uppercase tracking-[0.14em] text-fg-faint font-mono">
                <th className="text-left py-2 font-medium pr-3">Created</th>
                <th className="text-left py-2 font-medium pr-3">Intent</th>
                <th className="text-left py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {activity.campaigns.map((c) => (
                <tr
                  key={c.id}
                  className="border-b border-border-subtle last:border-b-0"
                >
                  <td className="py-2 pr-3 font-mono text-fg-mono whitespace-nowrap">
                    {formatRelative(c.createdAt)}
                  </td>
                  <td className="py-2 pr-3 text-fg-muted">{c.intent}</td>
                  <td className="py-2 font-mono text-[12px] uppercase tracking-[0.14em] text-fg-default">
                    {c.status}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Block>
      )}
    </>
  );
}

function VoicePanel({ persona }: { persona: Persona }) {
  return (
    <>
      <Block label="Backstory">
        <p className="text-[14px] text-fg-default leading-6">
          {persona.backstory}
        </p>
      </Block>
      <Block label="Style">
        <p className="text-[14px] text-fg-default leading-6">{persona.style}</p>
      </Block>
      {persona.vocabularyQuirks.length > 0 && (
        <Block label="Vocabulary quirks">
          <Tags items={persona.vocabularyQuirks} />
        </Block>
      )}
      {persona.topicFocus.length > 0 && (
        <Block label="Topic focus">
          <Tags items={persona.topicFocus} />
        </Block>
      )}
      {persona.examples.length > 0 && (
        <Block label="Sample posts">
          <ol className="flex flex-col gap-2">
            {persona.examples.map((ex, i) => (
              <li
                key={i}
                className="flex gap-3 text-[14px] leading-5 border-l-2 border-border-default pl-3"
              >
                <span className="font-mono text-[12px] text-fg-faint w-5 tabular-nums shrink-0">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span className="text-fg-default italic">
                  &ldquo;{ex}&rdquo;
                </span>
              </li>
            ))}
          </ol>
        </Block>
      )}
    </>
  );
}

function NetworkPanel({
  persona,
  personasById,
}: {
  persona: Persona;
  personasById: Map<string, Persona>;
}) {
  if (persona.knows.length === 0) {
    return (
      <Block>
        <p className="text-[14px] text-fg-faint italic">
          {persona.name} operates alone — no corroborating agents declared.
        </p>
      </Block>
    );
  }
  return (
    <Block label="Knows">
      <div className="grid grid-cols-2 gap-2">
        {persona.knows.map((kid) => {
          const k = personasById.get(kid);
          return (
            <Link
              key={kid}
              href={{ pathname: "/personas", query: { p: kid } }}
              className="border border-border-default bg-bg-base hover:bg-bg-hover px-3 py-2 transition-colors"
            >
              <div className="text-[14px] text-fg-default">{k?.name ?? kid}</div>
              <div className="text-[12px] text-fg-faint">
                {k?.geoAnchor ?? "—"} · {k?.language ?? "—"}
              </div>
            </Link>
          );
        })}
      </div>
      <p className="mt-3 text-[12px] text-fg-faint italic">
        Backstop coordination dispatches corroborating posts from these
        agents after the seed lands.
      </p>
    </Block>
  );
}

function Stat({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: number;
  tone?: "default" | "pass" | "warn";
}) {
  const valueColor =
    tone === "pass"
      ? "text-pass-fg"
      : tone === "warn"
        ? "text-warn-fg"
        : "text-fg-default";
  return (
    <div className="border border-border-subtle bg-bg-base px-3 py-2">
      <div className="text-[12px] uppercase tracking-[0.14em] text-fg-faint font-mono">
        {label}
      </div>
      <div className={`mt-1 text-xl font-medium tabular-nums ${valueColor}`}>
        {value}
      </div>
    </div>
  );
}

function Tags({ items }: { items: string[] }) {
  return (
    <div className="flex flex-wrap gap-1">
      {items.map((t, i) => (
        <span
          key={i}
          className="inline-block border border-border-default bg-bg-base px-2 py-[2px] text-[13px] text-fg-mono font-mono"
        >
          {t}
        </span>
      ))}
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
