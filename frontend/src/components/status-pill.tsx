import type { Mission } from "@/lib/foundry";

const COPY: Record<Mission["status"], { label: string; tone: string }> = {
  draft:            { label: "DRAFT",            tone: "neutral" },
  pending_approval: { label: "PENDING APPROVAL", tone: "warn" },
  executing:        { label: "EXECUTING",        tone: "info" },
  completed:        { label: "COMPLETED",        tone: "pass" },
  failed:           { label: "FAILED",           tone: "fail" },
  aborted:          { label: "ABORTED",          tone: "neutral" },
};

const TONE_CLASS: Record<string, string> = {
  neutral: "bg-neutral-bg text-neutral-fg border-neutral-border",
  warn:    "bg-warn-bg text-warn-fg border-warn-border",
  info:    "bg-info-bg text-info-fg border-info-border",
  pass:    "bg-pass-bg text-pass-fg border-pass-border",
  fail:    "bg-fail-bg text-fail-fg border-fail-border",
};

export function StatusPill({
  status,
  size = "sm",
}: {
  status: Mission["status"];
  size?: "sm" | "md";
}) {
  const c = COPY[status];
  const sizing =
    size === "md"
      ? "px-3 py-1 text-[11px] tracking-[0.16em]"
      : "px-2 py-[2px] text-[10px] tracking-[0.14em]";
  return (
    <span
      className={`inline-block border font-mono font-medium uppercase ${TONE_CLASS[c.tone]} ${sizing}`}
    >
      {c.label}
    </span>
  );
}
