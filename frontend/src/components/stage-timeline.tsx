import type { Stage } from "@/lib/foundry";

const STAGE_LABEL: Record<string, string> = {
  validated: "VALIDATED",
  persona_generated: "PERSONA FORGED",
  artifact_selected: "ARTIFACT SELECTED",
  watermark_strip: "WATERMARK STRIPPED",
  exif_transplant: "EXIF TRANSPLANTED",
  provenance_check: "PROVENANCE GRADED",
  delivered: "DELIVERY",
};

const ICON: Record<string, string> = {
  ok: "✓",
  skipped: "·",
  error: "✗",
};

const ICON_TONE: Record<string, string> = {
  ok: "text-pass-fg",
  skipped: "text-fg-faint",
  error: "text-fail-fg",
};

function relativeTime(iso: string): string {
  if (!iso) return "—";
  // Just show the wall time portion in mono — relative is too chatty
  // for an audit trail.
  try {
    const d = new Date(iso);
    return d.toISOString().slice(11, 19) + "Z";
  } catch {
    return iso;
  }
}

export function StageTimeline({ stages }: { stages: Stage[] }) {
  if (stages.length === 0) {
    return (
      <p className="text-fg-faint italic text-sm">
        No stage events recorded for this mission.
      </p>
    );
  }
  return (
    <ol className="border border-border-subtle bg-bg-panel divide-y divide-border-subtle">
      {stages.map((s, i) => {
        const tone = s.status ?? "ok";
        return (
          <li
            key={`${s.stage}-${i}`}
            className="grid grid-cols-[24px_140px_72px_1fr] items-baseline gap-3 px-4 py-2 hover:bg-bg-hover transition-colors"
          >
            <span
              aria-label={`status ${tone}`}
              className={`font-mono text-base ${ICON_TONE[tone] ?? "text-fg-muted"}`}
            >
              {ICON[tone] ?? "·"}
            </span>
            <span className="font-mono text-[11px] tracking-[0.12em] text-fg-default">
              {STAGE_LABEL[s.stage] ?? s.stage.toUpperCase()}
            </span>
            <span className="font-mono text-[10px] text-fg-faint tabular-nums">
              {relativeTime(s.ts)}
            </span>
            <span className="text-[12px] text-fg-muted italic">
              {s.summary ?? "—"}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
