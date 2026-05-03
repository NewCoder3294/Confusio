/**
 * Stat tile — single number + uppercase label. Editorial typography,
 * no sparklines, no gradients, no emoji. Reads like a SITREP figure.
 */
export function StatTile({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: string;
  value: string | number;
  hint?: string;
  tone?: "default" | "info" | "warn";
}) {
  const valueColor =
    tone === "info"
      ? "text-info-fg"
      : tone === "warn"
        ? "text-warn-fg"
        : "text-fg-default";
  return (
    <div className="border border-border-subtle bg-bg-panel px-5 py-3 flex flex-col">
      <div className="text-[12px] uppercase tracking-[0.18em] text-fg-faint font-mono">
        {label}
      </div>
      <div className={`mt-1 text-3xl font-medium tabular-nums ${valueColor}`}>
        {value}
      </div>
      {hint && (
        <div className="text-[12px] uppercase tracking-[0.14em] text-fg-faint/80 font-mono mt-auto pt-2">
          {hint}
        </div>
      )}
    </div>
  );
}
