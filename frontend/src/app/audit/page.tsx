import { getDashboardSnapshot, type Channel, type Mission } from "@/lib/foundry";
import { StatusPill } from "@/components/status-pill";
import { PageHeader } from "@/components/surfaces";

export default async function AuthorizationAndAuditPage() {
  const snap = await getDashboardSnapshot();
  const channels = Array.from(snap.channelById.values()).sort((a, b) =>
    a.displayName.localeCompare(b.displayName),
  );
  const missions = snap.missions;
  const counts = {
    total: missions.length,
    completed: missions.filter((m) => m.status === "completed").length,
    failed: missions.filter((m) => m.status === "failed").length,
    aborted: missions.filter((m) => m.status === "aborted").length,
  };
  const sandboxCount = channels.filter((c) => c.isSandbox).length;

  return (
    <>
      <PageHeader
        eyebrow="Title 10 §1631 — Military Information Operations"
        title="Authorization & Audit"
        brief={`Foreign-targeted IO under U.S. Army intelligence authority. Live delivery disabled — every mission runs against ${sandboxCount} sandbox endpoints with full audit recording.`}
      />
      <div className="flex-1 min-h-0 overflow-y-auto">
        <div className="w-full mx-auto px-6 py-4 grid grid-cols-[1fr_320px] gap-4">
          <div className="flex flex-col gap-4">
            <CountStrip counts={counts} />
            <AuditTrail missions={missions} channelById={snap.channelById} />
          </div>
          <div className="flex flex-col gap-4">
            <AuthorityChain />
            <ChannelAllowlist channels={channels} />
          </div>
        </div>
      </div>
    </>
  );
}

/* ─────────────────────────────────────────────────────────────────────── */

function LegalBanner({ channels }: { channels: Channel[] }) {
  const sandboxCount = channels.filter((c) => c.isSandbox).length;
  return (
    <section className="border-b border-border-subtle bg-bg-panel">
      <div className="mx-auto px-6 py-5">
        <div className="font-mono text-[10px] tracking-[0.18em] text-classified uppercase">
          Authorization Statement — Operator Console
        </div>
        <h1 className="mt-1 text-2xl text-fg-default tracking-wide font-medium">
          Title 10 § 1631 — Military Information Operations
        </h1>
        <p className="mt-2 text-[13px] text-fg-muted leading-6 max-w-[820px]">
          This system operates under U.S. Army intelligence authority for
          foreign-targeted military information operations. Targeting is
          restricted to non-U.S. persons via sandbox-only channels. Live
          delivery is disabled in this build; every mission runs against
          sandbox endpoints with full audit recording.
        </p>
        <dl className="mt-4 grid grid-cols-4 gap-4 text-[12px]">
          <FactCell
            label="Authority"
            value="Title 10 §1631"
            sub="Military intelligence"
          />
          <FactCell
            label="Targeting"
            value="Foreign actors"
            sub="No domestic or U.S. persons"
          />
          <FactCell
            label="Sandbox endpoints"
            value={`${sandboxCount} channels`}
            sub="Allowlist enforced at engine"
          />
          <FactCell
            label="Live delivery"
            value="Disabled"
            sub="dry_run = true on every mission"
          />
        </dl>
      </div>
    </section>
  );
}

function FactCell({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="border border-border-subtle bg-bg-base px-3 py-2">
      <div className="text-[10px] uppercase tracking-[0.16em] text-fg-faint font-mono">
        {label}
      </div>
      <div className="mt-[2px] text-[14px] text-fg-default font-medium">
        {value}
      </div>
      {sub && (
        <div className="mt-[2px] text-[10px] text-fg-faint italic">{sub}</div>
      )}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────── */

function CountStrip({
  counts,
}: {
  counts: { total: number; completed: number; failed: number; aborted: number };
}) {
  return (
    <div className="grid grid-cols-4 gap-3">
      <Tally label="Total missions" value={counts.total} />
      <Tally label="Completed" value={counts.completed} tone="pass" />
      <Tally label="Failed" value={counts.failed} tone="fail" />
      <Tally label="Aborted" value={counts.aborted} tone="neutral" />
    </div>
  );
}

function Tally({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: number;
  tone?: "default" | "pass" | "fail" | "neutral";
}) {
  const valueColor =
    tone === "pass"
      ? "text-pass-fg"
      : tone === "fail"
        ? "text-fail-fg"
        : tone === "neutral"
          ? "text-fg-muted"
          : "text-fg-default";
  return (
    <div className="border border-border-subtle bg-bg-panel px-4 py-3">
      <div className="text-[10px] uppercase tracking-[0.16em] text-fg-faint font-mono">
        {label}
      </div>
      <div className={`mt-1 text-2xl font-medium tabular-nums ${valueColor}`}>
        {value}
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────── */

function AuditTrail({
  missions,
  channelById,
}: {
  missions: Mission[];
  channelById: Map<string, Channel>;
}) {
  return (
    <section>
      <div className="flex items-baseline justify-between mb-2">
        <h2 className="text-[11px] font-mono uppercase tracking-[0.18em] text-fg-faint">
          Mission audit trail
        </h2>
        <span className="text-[10px] font-mono text-fg-faint">
          Append-only · sorted by created descending
        </span>
      </div>
      <div className="border border-border-subtle bg-bg-panel">
        <table className="w-full text-[12px]">
          <thead>
            <tr className="border-b border-border-subtle text-[10px] uppercase tracking-[0.14em] text-fg-faint font-mono">
              <th className="text-left px-3 py-2 font-medium">Created</th>
              <th className="text-left px-3 py-2 font-medium">Mission ID</th>
              <th className="text-left px-3 py-2 font-medium">Operator</th>
              <th className="text-left px-3 py-2 font-medium">Target</th>
              <th className="text-left px-3 py-2 font-medium">Status</th>
              <th className="text-left px-3 py-2 font-medium">Dry run</th>
              <th className="text-left px-3 py-2 font-medium">Failure</th>
            </tr>
          </thead>
          <tbody>
            {missions.map((m) => {
              const channel = channelById.get(m.targetChannelId);
              return (
                <tr
                  key={m.missionId}
                  className="border-b border-border-subtle last:border-b-0 hover:bg-bg-hover"
                >
                  <td className="px-3 py-2 font-mono text-fg-mono whitespace-nowrap">
                    {fmt(m.createdAt)}
                  </td>
                  <td className="px-3 py-2 font-mono text-fg-default">
                    {m.missionId}
                  </td>
                  <td className="px-3 py-2 font-mono text-fg-muted">
                    {m.operator}
                  </td>
                  <td className="px-3 py-2 text-fg-muted">
                    {channel?.displayName ?? m.targetChannelId}
                  </td>
                  <td className="px-3 py-2">
                    <StatusPill status={m.status} />
                  </td>
                  <td className="px-3 py-2 font-mono text-fg-mono">
                    {m.dryRun ? "yes" : "no"}
                  </td>
                  <td className="px-3 py-2 font-mono text-[11px] text-fail-fg/80">
                    {m.failureCode ?? ""}
                  </td>
                </tr>
              );
            })}
            {missions.length === 0 && (
              <tr>
                <td
                  colSpan={7}
                  className="px-3 py-4 text-fg-faint italic text-center"
                >
                  No mission records.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/* ─────────────────────────────────────────────────────────────────────── */

function AuthorityChain() {
  const links = [
    { name: "J2", role: "Director of Intelligence" },
    { name: "OGC", role: "Office of General Counsel — review" },
    { name: "Operator", role: "Executing authority" },
  ];
  return (
    <section className="border border-border-subtle bg-bg-panel">
      <header className="px-4 py-2 border-b border-border-subtle">
        <h2 className="text-[11px] font-mono uppercase tracking-[0.18em] text-fg-faint">
          Approval chain
        </h2>
      </header>
      <ol className="px-4 py-3 flex flex-col gap-2">
        {links.map((l, i) => (
          <li key={l.name} className="flex items-baseline gap-3">
            <span className="font-mono text-[11px] text-fg-faint w-5 tabular-nums">
              {String(i + 1).padStart(2, "0")}.
            </span>
            <div>
              <div className="font-mono text-[12px] text-fg-default tracking-wide">
                {l.name}
              </div>
              <div className="text-[11px] text-fg-muted">{l.role}</div>
            </div>
          </li>
        ))}
      </ol>
      <footer className="px-4 py-2 border-t border-border-subtle">
        <p className="text-[10px] text-fg-faint italic">
          Recorded per mission. See audit trail.
        </p>
      </footer>
    </section>
  );
}

/* ─────────────────────────────────────────────────────────────────────── */

function ChannelAllowlist({ channels }: { channels: Channel[] }) {
  return (
    <section className="border border-border-subtle bg-bg-panel">
      <header className="px-4 py-2 border-b border-border-subtle">
        <h2 className="text-[11px] font-mono uppercase tracking-[0.18em] text-fg-faint">
          Sandbox channel allowlist
        </h2>
      </header>
      <ul className="divide-y divide-border-subtle">
        {channels.map((c) => (
          <li key={c.channel_id} className="px-4 py-2">
            <div className="flex items-baseline justify-between gap-2">
              <span className="font-mono text-[12px] text-fg-default">
                {c.displayName}
              </span>
              {c.isSandbox && (
                <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-pass-fg border border-pass-border bg-pass-bg px-2 py-[1px]">
                  SANDBOX
                </span>
              )}
            </div>
            {c.audienceProfile && (
              <div className="mt-[2px] text-[11px] text-fg-muted italic">
                {c.audienceProfile}
              </div>
            )}
          </li>
        ))}
        {channels.length === 0 && (
          <li className="px-4 py-3 text-fg-faint italic text-[11px]">
            No channels configured.
          </li>
        )}
      </ul>
      <footer className="px-4 py-2 border-t border-border-subtle">
        <p className="text-[10px] text-fg-faint italic">
          Source of truth: Foundry Ontology. Synced to engine via bridge.
        </p>
      </footer>
    </section>
  );
}

/* ─────────────────────────────────────────────────────────────────────── */

function fmt(iso: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toISOString().replace("T", " ").slice(0, 19) + "Z";
  } catch {
    return iso;
  }
}
