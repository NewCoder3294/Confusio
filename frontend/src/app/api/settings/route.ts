import "server-only";
import {
  readSettings,
  updateSettings,
  KNOWN_KEYS,
  type KnownKey,
} from "@/lib/settings";
import { revalidatePath } from "next/cache";

export async function GET() {
  const snap = await readSettings();
  return Response.json({ settings: snap });
}

export async function POST(req: Request) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return Response.json({ error: "Invalid JSON body." }, { status: 400 });
  }
  if (!body || typeof body !== "object") {
    return Response.json({ error: "Body must be an object." }, { status: 400 });
  }

  const r = body as Record<string, unknown>;
  const updates: Partial<Record<KnownKey, string>> = {};
  const known = new Set<string>(KNOWN_KEYS);
  const rejected: string[] = [];

  for (const [k, v] of Object.entries(r)) {
    if (!known.has(k)) {
      rejected.push(k);
      continue;
    }
    if (typeof v !== "string") {
      return Response.json(
        { error: `Value for "${k}" must be a string.` },
        { status: 400 },
      );
    }
    // Reject newlines in values — would corrupt the .env file.
    if (/[\r\n]/.test(v)) {
      return Response.json(
        { error: `Value for "${k}" must not contain newlines.` },
        { status: 400 },
      );
    }
    updates[k as KnownKey] = v;
  }

  if (Object.keys(updates).length === 0) {
    return Response.json(
      { error: "No known keys provided.", rejected },
      { status: 400 },
    );
  }

  try {
    await updateSettings(updates);
  } catch (e) {
    return Response.json(
      { error: `write failed: ${(e as Error).message}` },
      { status: 500 },
    );
  }

  revalidatePath("/settings");
  const snap = await readSettings();
  return Response.json({ ok: true, settings: snap, rejected });
}
