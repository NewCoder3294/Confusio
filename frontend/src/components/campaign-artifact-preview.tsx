"use client";

import { useEffect, useState } from "react";

/**
 * Renders the generated artifact for a mission. While DALL-E is still working
 * the file 404s; this component polls the URL until the bytes appear, then
 * shows them. No background job — purely client-side polling on the route.
 */
export function CampaignArtifactPreview({
  missionId,
  prompt,
}: {
  missionId: string;
  prompt: string;
}) {
  const [ready, setReady] = useState(false);
  const [bust, setBust] = useState(() => Date.now());

  useEffect(() => {
    let cancelled = false;
    const url = `/api/campaign-image/${encodeURIComponent(missionId)}`;
    async function check() {
      if (cancelled) return;
      try {
        const res = await fetch(url, { method: "HEAD", cache: "no-store" });
        if (cancelled) return;
        if (res.ok) {
          setReady(true);
          setBust(Date.now());
          return;
        }
      } catch {
        // network blip — retry
      }
      setTimeout(check, 4000);
    }
    setReady(false);
    check();
    return () => {
      cancelled = true;
    };
  }, [missionId]);

  if (!ready) {
    return (
      <div className="aspect-video bg-bg-base border border-border-subtle flex flex-col items-center justify-center gap-2 px-6">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-info-fg animate-pulse">
          Generating · DALL-E 3
        </div>
        <p className="text-[11px] text-fg-faint italic text-center max-w-[420px]">
          {prompt}
        </p>
        <div className="font-mono text-[9px] text-fg-faint mt-1">
          Polls every 4s · usually ready in 10–25s
        </div>
      </div>
    );
  }
  return (
    <div className="bg-bg-base border border-border-subtle flex items-center justify-center overflow-hidden">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={`/api/campaign-image/${encodeURIComponent(missionId)}?t=${bust}`}
        alt={`Mission ${missionId} artifact`}
        className="max-h-[360px] w-auto object-contain"
      />
    </div>
  );
}
