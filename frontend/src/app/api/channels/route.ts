import "server-only";
import { applyAction } from "@/lib/foundry";
import { revalidatePath } from "next/cache";

type ChannelInput = {
  channel_id: string;
  platform: string;
  displayName: string;
  isSandbox: boolean;
  audienceProfile: string;
};

function parseInput(o: unknown): { ok: true; value: ChannelInput } | { ok: false; error: string } {
  if (!o || typeof o !== "object") return { ok: false, error: "Body must be JSON object." };
  const r = o as Record<string, unknown>;
  const id = String(r.channel_id ?? "").trim();
  if (!/^[a-z0-9_]{3,40}$/i.test(id)) {
    return { ok: false, error: "channel_id must be 3-40 chars, alphanumeric + underscore." };
  }
  const platform = String(r.platform ?? "telegram").trim() || "telegram";
  const displayName = String(r.displayName ?? "").trim();
  if (!displayName) return { ok: false, error: "displayName is required." };
  const audienceProfile = String(r.audienceProfile ?? "").trim();
  if (!audienceProfile) return { ok: false, error: "audienceProfile is required." };
  // Force isSandbox = true. Per PALANTIR_BRIEF §10 and PRODUCT.md, the
  // operator UI cannot create non-sandbox channels — that's an out-of-band
  // change requiring legal sign-off.
  return {
    ok: true,
    value: { channel_id: id, platform, displayName, isSandbox: true, audienceProfile },
  };
}

export async function POST(req: Request) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return Response.json({ error: "Invalid JSON body." }, { status: 400 });
  }
  const parsed = parseInput(body);
  if (!parsed.ok) return Response.json({ error: parsed.error }, { status: 400 });

  try {
    const r = await applyAction("create-channel", parsed.value);
    revalidatePath("/channels");
    revalidatePath("/audit");
    return Response.json({ ok: true, channel: parsed.value, foundry: r });
  } catch (e) {
    return Response.json(
      { error: `create-channel failed: ${(e as Error).message}` },
      { status: 502 },
    );
  }
}
