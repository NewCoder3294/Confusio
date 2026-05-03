import { getSystemStatus, type SystemStatus } from "@/lib/system-status";

export async function SystemFooter() {
  const status = await getSystemStatus();
  return (
    <footer className="border-t border-border-subtle bg-bg-panel">
      <div className="mx-auto px-6 py-2 flex items-center justify-between text-[12px] font-mono text-fg-faint uppercase tracking-[0.16em]">
        <div className="flex items-center gap-4">
          <span>OPERATOR: {status.operator}</span>
          <Indicator label="Foundry" detail={foundryDetail(status.foundry)} ok={status.foundry.ok} />
          <Indicator label="Engine DB" detail={engineDetail(status.engineDb)} ok={status.engineDb.ok} />
          <Indicator label="Bridge" detail={bridgeDetail(status.bridge)} ok={status.bridge.ok} />
        </div>
        <div className="flex items-center gap-4">
          <span>{status.buildLabel}</span>
          <span>RECORD-OF-ACTIONS // APPEND-ONLY</span>
        </div>
      </div>
    </footer>
  );
}

function Indicator({
  label,
  detail,
  ok,
}: {
  label: string;
  detail: string;
  ok: boolean;
}) {
  return (
    <span className="flex items-baseline gap-1" title={detail}>
      <span
        aria-hidden="true"
        className={`inline-block w-[6px] h-[6px] rounded-full ${
          ok ? "bg-pass-fg" : "bg-fail-fg"
        }`}
      />
      <span>
        {label}: <span className="text-fg-mono normal-case tracking-normal">{detail}</span>
      </span>
    </span>
  );
}

function foundryDetail(f: SystemStatus["foundry"]): string {
  if (!f.ok) return "unreachable";
  return `${f.missions} missions, synced ${shortTs(f.lastSyncIso)}`;
}

function engineDetail(e: SystemStatus["engineDb"]): string {
  if (!e.ok) return "missing";
  const kb = (e.sizeBytes / 1024).toFixed(0);
  return `${kb}KB, mtime ${shortTs(e.mtimeIso)}`;
}

function bridgeDetail(b: SystemStatus["bridge"]): string {
  if (!b.ok && b.lastBeatIso === null) return "no heartbeat";
  if (!b.ok) return `stale ${Math.round(b.secondsAgo ?? 0)}s`;
  return `beat ${Math.round(b.secondsAgo ?? 0)}s ago`;
}

function shortTs(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toISOString().slice(11, 19) + "Z";
  } catch {
    return "—";
  }
}
