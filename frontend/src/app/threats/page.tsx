import Link from "next/link";
import {
  listThreatRecords,
  type ThreatRecord,
} from "@/lib/threats";
import { PageHeader } from "@/components/surfaces";

export const metadata = {
  title: "Mendacity — Threat Library",
};

export default async function ThreatLibraryPage({
  searchParams,
}: {
  searchParams: Promise<{ [k: string]: string | string[] | undefined }>;
}) {
  const sp = await searchParams;
  const filter = typeof sp.filter === "string" ? sp.filter : "all";

  const all = await listThreatRecords();
  const counts = countByVerdict(all);
  const filtered =
    filter === "synthetic"
      ? all.filter((r) => r.report.verdict.label === "SUSPECTED_SYNTHETIC")
      : filter === "inconclusive"
        ? all.filter((r) => r.report.verdict.label === "INCONCLUSIVE")
        : filter === "authentic"
          ? all.filter((r) => r.report.verdict.label === "SUSPECTED_AUTHENTIC")
          : all;

  return (
    <>
      <PageHeader
        eyebrow="Defensive — Triage archive"
        title="Threat Library"
        brief="Append-only record of every Intel Inbox triage. Records are immutable; correction goes via a new triage."
      />
      <div className="flex-1 min-h-0 flex flex-col">
        <div className="flex-1 min-h-0 w-full mx-auto px-6 py-4 flex flex-col gap-4">
          <div className="grid grid-cols-4 gap-2 shrink-0">
            <Tally href="/threats" label="Total" value={counts.total} active={filter === "all"} />
            <Tally
              href="/threats?filter=synthetic"
              label="Synthetic"
              value={counts.synthetic}
              active={filter === "synthetic"}
              tone="fail"
            />
            <Tally
              href="/threats?filter=inconclusive"
              label="Inconclusive"
              value={counts.inconclusive}
              active={filter === "inconclusive"}
              tone="warn"
            />
            <Tally
              href="/threats?filter=authentic"
              label="Authentic"
              value={counts.authentic}
              active={filter === "authentic"}
              tone="pass"
            />
          </div>
          {filtered.length === 0 ? (
            <EmptyLibrary filter={filter} totalAll={counts.total} />
          ) : (
            <ThreatTable records={filtered} />
          )}
        </div>
      </div>
    </>
  );
}

/* ─────────────────────────────────────────────────────────────────────── */

function countByVerdict(records: ThreatRecord[]) {
  let synthetic = 0,
    inconclusive = 0,
    authentic = 0;
  for (const r of records) {
    const v = r.report.verdict.label;
    if (v === "SUSPECTED_SYNTHETIC") synthetic++;
    else if (v === "INCONCLUSIVE") inconclusive++;
    else if (v === "SUSPECTED_AUTHENTIC") authentic++;
  }
  return { total: records.length, synthetic, inconclusive, authentic };
}

function Tally({
  href,
  label,
  value,
  tone = "default",
  active,
}: {
  href: string;
  label: string;
  value: number;
  tone?: "default" | "pass" | "warn" | "fail";
  active: boolean;
}) {
  const valueColor =
    tone === "fail"
      ? "text-fail-fg"
      : tone === "warn"
        ? "text-warn-fg"
        : tone === "pass"
          ? "text-pass-fg"
          : "text-fg-default";
  return (
    <Link
      href={href}
      scroll={false}
      className={`border bg-bg-panel px-4 py-3 transition-colors hover:bg-bg-hover ${
        active
          ? "border-info-fg bg-bg-elevated"
          : "border-border-subtle"
      }`}
    >
      <div className="text-[10px] uppercase tracking-[0.16em] text-fg-faint font-mono">
        {label}
      </div>
      <div className={`mt-1 text-2xl font-medium tabular-nums ${valueColor}`}>
        {value}
      </div>
    </Link>
  );
}

function EmptyLibrary({
  filter,
  totalAll,
}: {
  filter: string;
  totalAll: number;
}) {
  return (
    <div className="border border-border-subtle bg-bg-panel py-16 text-center">
      <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-fg-faint">
        {filter === "all"
          ? "No triages recorded"
          : `No records match filter "${filter}"`}
      </div>
      <p className="mt-3 text-[13px] text-fg-muted leading-6 max-w-md mx-auto">
        {totalAll === 0 ? (
          <>
            Submit a suspect image at{" "}
            <Link href="/intel" className="text-info-fg underline">
              /intel
            </Link>{" "}
            and it will appear here.
          </>
        ) : (
          <>
            <Link href="/threats" className="text-info-fg underline">
              Clear filter
            </Link>{" "}
            to see all {totalAll} record{totalAll === 1 ? "" : "s"}.
          </>
        )}
      </p>
    </div>
  );
}

function ThreatTable({ records }: { records: ThreatRecord[] }) {
  return (
    <div className="flex-1 min-h-0 overflow-y-auto border border-border-subtle bg-bg-panel">
      <table className="w-full text-[12px]">
        <thead>
          <tr className="border-b border-border-subtle text-[10px] uppercase tracking-[0.14em] text-fg-faint font-mono">
            <th className="text-left px-3 py-2 font-medium">Received</th>
            <th className="text-left px-3 py-2 font-medium">Filename</th>
            <th className="text-left px-3 py-2 font-medium">Verdict</th>
            <th className="text-left px-3 py-2 font-medium">Confidence</th>
            <th className="text-left px-3 py-2 font-medium">Reviewer</th>
            <th className="text-left px-3 py-2 font-medium">SHA-256</th>
            <th className="text-left px-3 py-2 font-medium">Top driver</th>
          </tr>
        </thead>
        <tbody>
          {records.map((r) => (
            <ThreatRow key={r.id} record={r} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ThreatRow({ record }: { record: ThreatRecord }) {
  const v = record.report.verdict;
  const sha = record.report.meta.sha256 ?? "";
  return (
    <tr className="border-b border-border-subtle last:border-b-0 hover:bg-bg-hover">
      <td className="px-3 py-2 font-mono text-fg-mono whitespace-nowrap">
        {formatRelative(record.receivedAt)}
      </td>
      <td className="px-3 py-2 text-fg-default truncate max-w-[200px]">
        {record.filename}
      </td>
      <td className="px-3 py-2">
        <VerdictPill label={v.label} />
      </td>
      <td className="px-3 py-2 font-mono text-[11px] uppercase tracking-[0.14em] text-fg-muted">
        {v.confidence} · {v.score >= 0 ? "+" : ""}
        {v.score}
      </td>
      <td className="px-3 py-2 font-mono text-[11px] text-fg-muted">
        {record.reviewer}
      </td>
      <td
        className="px-3 py-2 font-mono text-[10px] text-fg-faint truncate max-w-[140px]"
        title={sha}
      >
        {sha.slice(0, 16)}…
      </td>
      <td className="px-3 py-2 text-[11px] text-fg-muted italic truncate max-w-[420px]">
        {v.drivers[0] ?? "—"}
      </td>
    </tr>
  );
}

function VerdictPill({ label }: { label: string }) {
  const TONE: Record<string, string> = {
    SUSPECTED_SYNTHETIC: "border-fail-border bg-fail-bg text-fail-fg",
    INCONCLUSIVE: "border-warn-border bg-warn-bg text-warn-fg",
    SUSPECTED_AUTHENTIC: "border-pass-border bg-pass-bg text-pass-fg",
  };
  const COPY: Record<string, string> = {
    SUSPECTED_SYNTHETIC: "SYNTHETIC",
    INCONCLUSIVE: "INCONCLUSIVE",
    SUSPECTED_AUTHENTIC: "AUTHENTIC",
  };
  return (
    <span
      className={`inline-block border font-mono font-medium uppercase px-2 py-[2px] text-[10px] tracking-[0.14em] ${TONE[label] ?? "border-border-default bg-neutral-bg text-neutral-fg"}`}
    >
      {COPY[label] ?? label}
    </span>
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
