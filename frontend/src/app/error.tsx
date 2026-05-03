"use client";

import { useEffect } from "react";

/**
 * Segment-level error boundary. Catches any unhandled error from the
 * routes underneath /app and presents it in dossier style rather than
 * the React dev overlay.
 */
export default function SegmentError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[mendacity ui error]", error);
  }, [error]);

  return (
    <div className="flex-1 flex items-center justify-center p-6">
      <div className="max-w-2xl border border-fail-border bg-fail-bg/40 p-6 flex flex-col gap-4">
        <div>
          <div className="font-mono text-[12px] uppercase tracking-[0.18em] text-fail-fg">
            Console fault — segment isolated
          </div>
          <h1 className="mt-1 text-xl text-fg-default font-medium tracking-wide">
            This view could not render.
          </h1>
          <p className="mt-2 text-[14px] text-fg-muted leading-6">
            The current segment threw an uncaught error. Other surfaces
            remain operational; the audit trail is unaffected. If this
            persists across retry, snapshot the diagnostics below and
            escalate per the runbook&apos;s incident response procedure.
          </p>
        </div>
        <div className="border border-border-subtle bg-bg-base p-3 font-mono text-[13px] text-fg-mono whitespace-pre-wrap break-all">
          {error.message || "(no message)"}
          {error.digest && (
            <div className="mt-2 text-fg-faint">digest: {error.digest}</div>
          )}
        </div>
        <div className="flex gap-2">
          <button
            onClick={reset}
            className="border border-info-border bg-info-bg px-4 py-2 font-mono text-[14px] uppercase tracking-[0.16em] text-info-fg hover:opacity-90"
          >
            Retry segment
          </button>
          <a
            href="/"
            className="border border-border-default bg-bg-elevated px-4 py-2 font-mono text-[14px] uppercase tracking-[0.16em] text-fg-default hover:bg-bg-hover"
          >
            Return to mission board
          </a>
        </div>
      </div>
    </div>
  );
}
