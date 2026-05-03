"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

export function DeleteAgentButton({
  agentId,
  agentName,
}: {
  agentId: string;
  agentName: string;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [referrers, setReferrers] = useState<string[]>([]);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setReferrers([]);
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  async function confirmDelete() {
    setBusy(true);
    setError(null);
    setReferrers([]);
    try {
      const res = await fetch(`/api/personas/${encodeURIComponent(agentId)}`, {
        method: "DELETE",
      });
      const body = await res.json();
      if (!res.ok) {
        setError(body.error || `HTTP ${res.status}`);
        if (Array.isArray(body.referrers)) setReferrers(body.referrers);
        return;
      }
      // Success — bounce to /personas with no selection.
      setOpen(false);
      router.push("/personas");
      router.refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="font-mono text-[10px] uppercase tracking-[0.14em] text-fail-fg hover:text-fg-default border border-fail-border/50 hover:bg-fail-bg/30 px-2 py-1 transition-colors"
        title={`Delete ${agentName}`}
      >
        ✕ Delete
      </button>
      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          onClick={(e) => {
            if (e.target === e.currentTarget && !busy) setOpen(false);
          }}
        >
          <div className="w-[480px] max-w-[92vw] border border-fail-border bg-bg-panel shadow-2xl">
            <header className="px-5 py-3 border-b border-border-default bg-bg-elevated">
              <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-fail-fg">
                Destructive action
              </div>
              <h2 className="text-[15px] font-medium text-fg-default tracking-wide mt-[1px]">
                Delete agent {agentName}?
              </h2>
            </header>

            <div className="px-5 py-4 flex flex-col gap-3 text-[12px] text-fg-muted leading-6">
              <p>
                Removes{" "}
                <span className="font-mono text-fg-default">
                  social/personas/{agentId}.json
                </span>
                . The engine will skip it on its next library reload.
              </p>
              <p className="text-[11px] text-fg-faint italic">
                The agent&rsquo;s session file, generated-post history, and any
                Foundry record are left untouched — clean those up out of band
                if you need a hard wipe.
              </p>

              {referrers.length > 0 && (
                <div className="border border-warn-border bg-warn-bg/20 px-3 py-2">
                  <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-warn-fg mb-1">
                    Blocked — referenced by
                  </div>
                  <ul className="font-mono text-[11px] text-fg-default list-disc pl-4">
                    {referrers.map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                  </ul>
                  <p className="mt-2 text-[10px] text-fg-faint italic">
                    Edit those agents&rsquo; <span className="font-mono">knows</span>{" "}
                    graph first, then retry.
                  </p>
                </div>
              )}

              {error && referrers.length === 0 && (
                <div className="border border-fail-border bg-fail-bg/40 px-3 py-2 text-fail-fg text-[11px] font-mono">
                  {error}
                </div>
              )}
            </div>

            <footer className="px-5 py-3 border-t border-border-default bg-bg-elevated flex items-center justify-end gap-2">
              <button
                onClick={() => setOpen(false)}
                disabled={busy}
                className="px-3 py-1 font-mono text-[11px] uppercase tracking-[0.14em] text-fg-muted hover:text-fg-default disabled:opacity-30"
              >
                Cancel
              </button>
              <button
                onClick={confirmDelete}
                disabled={busy}
                className="border border-fail-border bg-fail-bg/60 hover:bg-fail-bg px-4 py-1 font-mono text-[11px] uppercase tracking-[0.16em] text-fail-fg disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {busy ? "Deleting…" : "Delete agent"}
              </button>
            </footer>
          </div>
        </div>
      )}
    </>
  );
}
