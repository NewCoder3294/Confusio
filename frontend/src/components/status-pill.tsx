import type { Mission } from "@/lib/foundry";

const COPY: Record<Mission["status"], { label: string; tone: string }> = {
  draft:            { label: "DRAFT",     tone: "neutral" },
  pending_approval: { label: "PENDING",   tone: "warn" },
  executing:        { label: "EXECUTING", tone: "info" },
  completed:        { label: "COMPLETED", tone: "pass" },
  failed:           { label: "FAILED",    tone: "fail" },
  aborted:          { label: "ABORTED",   tone: "neutral" },
};

// Foundry-style status: a coloured dot + label, no pill chrome. Reads as
// data, not as decoration. Only `fail` keeps a saturated colour.
const TONE: Record<string, { dot: string; text: string }> = {
  neutral: { dot: "bg-fg-faint",  text: "text-fg-muted" },
  warn:    { dot: "bg-warn-fg",   text: "text-warn-fg" },
  info:    { dot: "bg-info-fg",   text: "text-info-fg" },
  pass:    { dot: "bg-pass-fg",   text: "text-pass-fg" },
  fail:    { dot: "bg-fail-fg",   text: "text-fail-fg" },
};

export function StatusPill({
  status,
  size = "sm",
}: {
  status: Mission["status"];
  size?: "sm" | "md";
}) {
  const c = COPY[status];
  const tone = TONE[c.tone];
  const sizing =
    size === "md"
      ? "text-[13px] tracking-[0.16em] gap-2"
      : "text-[12px] tracking-[0.14em] gap-[6px]";
  const isExecuting = status === "executing";
  return (
    <span
      className={`inline-flex items-center font-mono font-medium uppercase ${tone.text} ${sizing}`}
    >
      <span
        className={`inline-block w-[6px] h-[6px] rounded-full ${tone.dot} ${
          isExecuting ? "animate-pulse" : ""
        }`}
        aria-hidden="true"
      />
      {c.label}
    </span>
  );
}
