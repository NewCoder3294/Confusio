"use client";

import { useEffect, useState } from "react";

/**
 * Single artifact image with operator controls:
 *   - rotate (calls POST ?op=rotate&degrees=90 — re-rotates and re-renders)
 *   - regenerate (only for `local:` mission artifacts that lack a generated PNG)
 *
 * Self-polls the URL until the bytes appear so freshly-dispatched missions
 * show "Generating…" instead of a broken-image icon.
 */
export function ArtifactImage({
  // Either both of artifactId+variant (Foundry artifact) OR localMissionId
  // (local synthetic dispatch) must be provided.
  artifactId,
  variant,
  localMissionId,
  prompt,
  alt,
  heightClass = "h-[320px]",
}: {
  artifactId?: string;
  variant?: string;
  localMissionId?: string;
  prompt?: string;
  alt: string;
  heightClass?: string;
}) {
  const isLocal = Boolean(localMissionId);
  const baseUrl = isLocal
    ? `/api/campaign-image/${encodeURIComponent(localMissionId!)}`
    : `/api/artifact/${encodeURIComponent(artifactId!)}?variant=${encodeURIComponent(variant ?? "clean")}`;

  const [ready, setReady] = useState(!isLocal);
  const [bust, setBust] = useState(() => Date.now());
  const [busy, setBusy] = useState<"rotate" | "regen" | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Poll for the image if it's a local mission and not yet on disk.
  useEffect(() => {
    if (!isLocal) return;
    let cancelled = false;
    async function check() {
      if (cancelled) return;
      try {
        const res = await fetch(baseUrl, { method: "HEAD", cache: "no-store" });
        if (cancelled) return;
        if (res.ok) {
          setReady(true);
          setBust(Date.now());
          return;
        }
      } catch {
        // retry
      }
      setTimeout(check, 4000);
    }
    setReady(false);
    check();
    return () => {
      cancelled = true;
    };
  }, [isLocal, baseUrl]);

  async function rotate(deg: number) {
    setBusy("rotate");
    setError(null);
    try {
      const url = isLocal
        ? `${baseUrl}?op=rotate&degrees=${deg}`
        : baseUrl.includes("?")
          ? `${baseUrl}&op=rotate&degrees=${deg}`
          : `${baseUrl}?op=rotate&degrees=${deg}`;
      // For non-local, the endpoint is /api/artifact/<id>?variant=...; the
      // route accepts POST with degrees= and ignores GET-only params on POST.
      const target = isLocal
        ? `/api/campaign-image/${encodeURIComponent(localMissionId!)}?op=rotate&degrees=${deg}`
        : `/api/artifact/${encodeURIComponent(artifactId!)}?variant=${encodeURIComponent(variant ?? "clean")}&degrees=${deg}`;
      void url;
      const res = await fetch(target, { method: "POST" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error || `HTTP ${res.status}`);
      }
      setBust(Date.now());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function regenerate() {
    if (!isLocal) return;
    setBusy("regen");
    setError(null);
    setReady(false);
    try {
      const target = `/api/campaign-image/${encodeURIComponent(localMissionId!)}?op=regenerate`;
      const res = await fetch(target, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: prompt ? JSON.stringify({ prompt }) : "{}",
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error || `HTTP ${res.status}`);
      }
      // Force the polling loop to pick up the new file.
      setReady(true);
      setBust(Date.now());
    } catch (e) {
      setError((e as Error).message);
      setReady(true); // un-stick UI
    } finally {
      setBusy(null);
    }
  }

  if (isLocal && !ready) {
    return (
      <div className={`bg-bg-base border border-border-subtle flex flex-col items-center justify-center gap-2 px-6 ${heightClass}`}>
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-info-fg animate-pulse">
          {busy === "regen" ? "Regenerating · DALL-E 3" : "Generating · DALL-E 3"}
        </div>
        {prompt && (
          <p className="text-[11px] text-fg-faint italic text-center max-w-[420px]">
            {prompt}
          </p>
        )}
        <div className="font-mono text-[9px] text-fg-faint mt-1">
          Polls every 4s · usually ready in 10–25s
        </div>
        {error && (
          <button
            onClick={regenerate}
            className="mt-2 border border-fail-border text-fail-fg bg-fail-bg/30 px-3 py-1 font-mono text-[10px] uppercase tracking-[0.14em] hover:bg-fail-bg"
          >
            Retry · {error.slice(0, 60)}
          </button>
        )}
      </div>
    );
  }

  return (
    <div className={`bg-bg-base border border-border-subtle relative overflow-hidden ${heightClass}`}>
      <div className="absolute inset-0 flex items-center justify-center">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={`${baseUrl}${baseUrl.includes("?") ? "&" : "?"}t=${bust}`}
          alt={alt}
          className="max-h-full max-w-full object-contain"
          style={{ imageOrientation: "from-image" }}
        />
      </div>
      <div className="absolute top-2 right-2 flex items-center gap-1 bg-bg-panel/80 border border-border-default backdrop-blur-sm">
        <button
          onClick={() => rotate(90)}
          disabled={busy !== null}
          title="Rotate 90° clockwise"
          className="px-2 py-1 font-mono text-[11px] text-fg-default hover:text-info-fg disabled:opacity-40"
        >
          ↻
        </button>
        <button
          onClick={() => rotate(180)}
          disabled={busy !== null}
          title="Flip 180°"
          className="px-2 py-1 font-mono text-[11px] text-fg-default hover:text-info-fg disabled:opacity-40 border-l border-border-default"
        >
          ⇅
        </button>
        {isLocal && (
          <button
            onClick={regenerate}
            disabled={busy !== null}
            title="Regenerate this artifact"
            className="px-2 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-fg-muted hover:text-info-fg disabled:opacity-40 border-l border-border-default"
          >
            {busy === "regen" ? "…" : "regen"}
          </button>
        )}
      </div>
      {error && (
        <div className="absolute bottom-0 left-0 right-0 bg-fail-bg/70 border-t border-fail-border text-fail-fg font-mono text-[10px] px-3 py-1">
          {error}
        </div>
      )}
    </div>
  );
}
