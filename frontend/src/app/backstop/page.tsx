import { redirect } from "next/navigation";

/**
 * Backstop was merged into the Mission Board. Old links/bookmarks redirect
 * to the unified surface, preserving any campaign-id selection by mapping
 * `?c=c_<missionId>` → `?m=<missionId>`.
 */
export default async function BackstopRedirect({
  searchParams,
}: {
  searchParams: Promise<{ [k: string]: string | string[] | undefined }>;
}) {
  const sp = await searchParams;
  const c = typeof sp.c === "string" ? sp.c : undefined;
  const mid = c?.startsWith("c_") ? c.slice(2) : c;
  redirect(mid ? `/?m=${encodeURIComponent(mid)}` : "/");
}
