"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/**
 * Polls the server component on a fixed interval. Used by the Backstop page so
 * scheduled corroborator posts visibly flip to "posted" on the timeline as
 * their staggered moment passes — no background job, no websocket.
 */
export function AutoRefresh({ intervalMs = 10000 }: { intervalMs?: number }) {
  const router = useRouter();
  useEffect(() => {
    const t = setInterval(() => router.refresh(), intervalMs);
    return () => clearInterval(t);
  }, [router, intervalMs]);
  return null;
}
