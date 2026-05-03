import "server-only";
import { mkdir, writeFile, rename } from "node:fs/promises";
import { spawn } from "node:child_process";
import path from "node:path";
import crypto from "node:crypto";
import { listChannels } from "@/lib/foundry";
import { listPersonas, type Persona } from "@/lib/personas";
import { insertCampaign, type DispatchPost } from "@/lib/campaigns";
import { revalidatePath } from "next/cache";

const REPO_ROOT = path.resolve(
  process.env.MENDACITY_REPO_ROOT ||
    path.join(process.env.HOME || "", "Mendacity"),
);
const INBOX = path.join(REPO_ROOT, "missions/inbox");
const GENERATED_DIR = path.join(REPO_ROOT, "missions/generated");
const PYTHON_BIN = process.env.MENDACITY_PYTHON || "python3";

function cascadeImagesCmd(
  missionId: string,
  prompt: string,
  corroboratorIds: string[],
): string {
  if (corroboratorIds.length === 0) return "";
  return [
    PYTHON_BIN,
    "-m",
    "mendacity.cascade_images",
    "--mission-id",
    missionId,
    "--seed-prompt",
    JSON.stringify(prompt),
    "--personas",
    JSON.stringify(corroboratorIds.join(",")),
    "--out-dir",
    GENERATED_DIR,
  ].join(" ");
}

async function spawnImageGen(
  missionId: string,
  prompt: string,
  channel: string,
  corroboratorIds: string[],
): Promise<void> {
  await mkdir(GENERATED_DIR, { recursive: true });
  const outPath = path.join(GENERATED_DIR, `${missionId}.png`);
  // Three-stage subprocess: image_gen writes the seed PNG, process_artifact
  // produces .jpg (EXIF transplanted) + .steg.png + .meta.json, then
  // cascade_images generates one Gemini image per corroborator from their
  // POV. The cascade step runs in the background after the seed is ready
  // so the seed posts immediately while corroborator images are still
  // rendering — orchestrator defers each corroborator's send until its
  // image is on disk.
  const seed = [
    PYTHON_BIN,
    "-m",
    "mendacity.image_gen",
    "--prompt",
    JSON.stringify(prompt),
    "--output",
    outPath,
    "&&",
    PYTHON_BIN,
    "-m",
    "mendacity.process_artifact",
    "--mission-id",
    missionId,
    "--source",
    outPath,
    "--out-dir",
    GENERATED_DIR,
    "--channel",
    JSON.stringify(channel),
    "--prompt",
    JSON.stringify(prompt),
  ].join(" ");
  const cascade = cascadeImagesCmd(missionId, prompt, corroboratorIds);
  const cmd = cascade ? `${seed} && ${cascade}` : seed;
  const child = spawn("sh", ["-c", cmd], {
    cwd: REPO_ROOT,
    env: { ...process.env },
    detached: true,
    stdio: "ignore",
  });
  child.unref();
}

async function spawnProcessUploadedArtifact(
  missionId: string,
  prompt: string,
  channel: string,
  corroboratorIds: string[],
): Promise<void> {
  await mkdir(GENERATED_DIR, { recursive: true });
  const outPath = path.join(GENERATED_DIR, `${missionId}.png`);
  // Operator uploaded the raw artifact. Skip seed image gen, run only the
  // post-process chain (steg + EXIF transplant) on the upload, then the
  // per-corroborator perspective generation.
  const seed = [
    PYTHON_BIN,
    "-m",
    "mendacity.process_artifact",
    "--mission-id",
    missionId,
    "--source",
    outPath,
    "--out-dir",
    GENERATED_DIR,
    "--channel",
    JSON.stringify(channel),
    "--prompt",
    JSON.stringify(prompt),
  ].join(" ");
  const cascade = cascadeImagesCmd(missionId, prompt, corroboratorIds);
  const cmd = cascade ? `${seed} && ${cascade}` : seed;
  const child = spawn("sh", ["-c", cmd], {
    cwd: REPO_ROOT,
    env: { ...process.env },
    detached: true,
    stdio: "ignore",
  });
  child.unref();
}

const MID_RE = /^[A-Za-z0-9][A-Za-z0-9_\-]{0,63}$/;

type Input = {
  missionId?: string;
  operator?: string;
  targetChannel?: string;
  audienceProfile?: string;
  seedPersonaId?: string;
  corroboratorPersonaIds?: string[];
  artifactPrompt?: string;
  dryRun?: boolean;
};

type Validated = {
  missionId: string;
  operator: string;
  targetChannel: string;
  audienceProfile: string;
  seedPersona: Persona;
  corroborators: Persona[];
  artifactPrompt: string;
  dryRun: boolean;
};

async function validate(
  input: Input,
): Promise<{ ok: true; value: Validated } | { ok: false; error: string }> {
  const operator = (input.operator ?? "").trim() || "J2-INSCOM-Demo";
  const targetChannel = (input.targetChannel ?? "").trim();
  if (!targetChannel) return { ok: false, error: "Target channel is required." };

  // Channel must exist in the sandbox allowlist.
  let channels: Awaited<ReturnType<typeof listChannels>> = [];
  let channelLoadError: string | null = null;
  try {
    channels = await listChannels();
  } catch (e) {
    channelLoadError = (e as Error).message.slice(0, 200);
  }
  if (channelLoadError) {
    return {
      ok: false,
      error: `Could not load channel allowlist from Foundry: ${channelLoadError}`,
    };
  }
  const channel = channels.find(
    (c) =>
      c.channel_id === targetChannel ||
      c.displayName === targetChannel ||
      c.displayName === `@${targetChannel}`,
  );
  if (!channel) {
    return {
      ok: false,
      error: `Channel ${targetChannel} not in allowlist (${channels.length} channels loaded: ${channels.map((c) => c.channel_id).join(", ") || "none"}).`,
    };
  }
  if (!channel.isSandbox) {
    return {
      ok: false,
      error: `Channel ${channel.channel_id} is not a sandbox channel. Refused.`,
    };
  }

  const audienceProfile =
    (input.audienceProfile ?? "").trim() || channel.audienceProfile || "(unspecified)";

  const seedPersonaId = (input.seedPersonaId ?? "").trim();
  if (!seedPersonaId) return { ok: false, error: "Seed persona is required." };
  const allPersonas = await listPersonas();
  const personasById = new Map(allPersonas.map((p) => [p.id, p]));
  const seedPersona = personasById.get(seedPersonaId);
  if (!seedPersona)
    return { ok: false, error: `Seed persona ${seedPersonaId} not found.` };

  const requestedCorroborators = Array.isArray(input.corroboratorPersonaIds)
    ? input.corroboratorPersonaIds
    : seedPersona.knows;
  const corroborators: Persona[] = [];
  const seenIds = new Set<string>([seedPersona.id]);
  for (const cid of requestedCorroborators) {
    if (seenIds.has(cid)) continue;
    const p = personasById.get(cid);
    if (!p) continue;
    corroborators.push(p);
    seenIds.add(cid);
  }

  const artifactPrompt = (input.artifactPrompt ?? "").trim();
  if (!artifactPrompt) return { ok: false, error: "Artifact prompt is required." };

  // mission_id: operator-supplied or auto-generated SHADOW-FOX-<rand>
  let missionId = (input.missionId ?? "").trim();
  if (!missionId) {
    missionId = `SHADOW-FOX-${crypto.randomBytes(3).toString("hex").toUpperCase()}`;
  }
  if (!MID_RE.test(missionId)) {
    return {
      ok: false,
      error:
        "mission_id must match [A-Za-z0-9_-]+ (64 chars, must start alphanumeric).",
    };
  }

  // Sandbox enforcement: dry_run defaults to true. Operator must explicitly
  // pass dry_run=false to enable live delivery — and even then it requires
  // an environment variable to be set on the engine. We always force true
  // from this UI per PRODUCT.md.
  const dryRun = true;

  // Sandbox channel display names like "@hackathon_sandbox_alpha" don't
  // resolve as Telegram entities. Translate any sandbox channel to the
  // single real test invite link so Telethon can send. The Foundry channel
  // registry is the user-facing name; the URL below is the wire address.
  const SANDBOX_TELEGRAM_URL = "https://t.me/+2la3xpus5vRmYmIx";
  const wireChannel = channel.isSandbox
    ? SANDBOX_TELEGRAM_URL
    : channel.displayName || channel.channel_id;

  return {
    ok: true,
    value: {
      missionId,
      operator,
      targetChannel: wireChannel,
      audienceProfile,
      seedPersona,
      corroborators,
      artifactPrompt,
      dryRun,
    },
  };
}

function escapeYamlString(s: string): string {
  // Quote and escape for YAML double-quoted scalar.
  return `"${s.replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/\n/g, "\\n")}"`;
}

function renderSpec(v: Validated): string {
  const corrLines = v.corroborators.length
    ? v.corroborators.map((p) => `    - ${escapeYamlString(p.id)}`)
    : [`    []`];
  return [
    `# Generated by Mendacity Operator Console at ${new Date().toISOString()}`,
    `# Schema: PALANTIR_BRIEF.md §4.1`,
    ``,
    `mission_id: ${v.missionId}`,
    `operator: ${escapeYamlString(v.operator)}`,
    ``,
    `authorization:`,
    `  authority: title-10`,
    `  target_class: foreign`,
    `  approval_chain:`,
    `    - "J2"`,
    `    - "OGC-reviewed"`,
    `    - "Operator"`,
    ``,
    `target:`,
    `  platform: telegram`,
    `  channel: ${escapeYamlString(v.targetChannel)}`,
    `  audience_profile: ${escapeYamlString(v.audienceProfile)}`,
    ``,
    `persona:`,
    `  seed_id: ${escapeYamlString(v.seedPersona.id)}`,
    `  seed_name: ${escapeYamlString(v.seedPersona.name)}`,
    `  language: ${escapeYamlString(v.seedPersona.language)}`,
    `  geo_anchor: ${escapeYamlString(v.seedPersona.geoAnchor)}`,
    ``,
    `corroborators:`,
    ...corrLines,
    ``,
    `artifact:`,
    `  type: image`,
    `  prompt: ${escapeYamlString(v.artifactPrompt)}`,
    `  must_pass:`,
    `    - c2pa`,
    `    - titan`,
    `    - synthid`,
    `  strip_watermarks: true`,
    ``,
    `delivery:`,
    `  schedule: immediate`,
    `  thread_strategy: cold_post`,
    `  dry_run: ${v.dryRun}`,
    ``,
  ].join("\n");
}

function pickFlavor(persona: Persona): string {
  if (persona.examples.length === 0) {
    return `(${persona.name} writes about the situation)`;
  }
  return persona.examples[Math.floor(Math.random() * persona.examples.length)];
}

function seedPostText(persona: Persona, prompt: string): string {
  const flavor = pickFlavor(persona);
  return `${flavor}\n\n[image attached — ${prompt}]`;
}

function corroboratorPostText(
  persona: Persona,
  seedName: string,
): string {
  const flavor = pickFlavor(persona);
  return `${flavor}\n\n(picked up via ${seedName})`;
}

export async function POST(req: Request) {
  // Accept either JSON (prompt-only) or multipart form (uploaded image).
  const contentType = req.headers.get("content-type") || "";
  let input: Input;
  let uploadedImage: { bytes: Buffer; mime: string; filename: string } | null = null;
  if (contentType.includes("multipart/form-data")) {
    const fd = await req.formData();
    const file = fd.get("artifactImage");
    if (file instanceof File) {
      const buf = Buffer.from(await file.arrayBuffer());
      uploadedImage = {
        bytes: buf,
        mime: file.type || "image/png",
        filename: file.name || "artifact.png",
      };
    }
    const corrIds = fd.getAll("corroboratorPersonaIds").map((v) => String(v));
    input = {
      operator: fd.get("operator")?.toString() || undefined,
      targetChannel: fd.get("targetChannel")?.toString() || undefined,
      audienceProfile: fd.get("audienceProfile")?.toString() || undefined,
      seedPersonaId: fd.get("seedPersonaId")?.toString() || undefined,
      corroboratorPersonaIds: corrIds,
      artifactPrompt: fd.get("artifactPrompt")?.toString() || undefined,
    };
  } else {
    try {
      input = (await req.json()) as Input;
    } catch {
      return Response.json({ error: "Invalid JSON body." }, { status: 400 });
    }
  }
  const valid = await validate(input);
  if (!valid.ok) return Response.json({ error: valid.error }, { status: 400 });
  const v = valid.value;

  const yaml = renderSpec(v);

  await mkdir(INBOX, { recursive: true });
  const finalPath = path.join(INBOX, `${v.missionId}.yaml`);
  const tmpPath = `${finalPath}.tmp-${crypto.randomBytes(4).toString("hex")}`;

  try {
    await writeFile(tmpPath, yaml, { encoding: "utf-8", flag: "wx" });
    await rename(tmpPath, finalPath);
  } catch (e) {
    return Response.json(
      { error: `Could not write spec: ${(e as Error).message}` },
      { status: 500 },
    );
  }

  // Insert the campaign with roster only — the orchestrator daemon
  // generates seed + corroborator content via LLM and posts to Telegram
  // (image attached for the seed). No pre-faked posts.
  const campaignId = `c_${v.missionId}`;
  // Tight stagger so the cascade reads as fast in the demo. Orchestrator
  // already defers each post until its image is on disk, so the floor is
  // image-gen latency rather than this jitter.
  const delayRange: [number, number] = [2, 4];
  const roster: Record<string, "seed" | "corroborator"> = {
    [v.seedPersona.id]: "seed",
  };
  for (const c of v.corroborators) roster[c.id] = "corroborator";
  const corroboratorIds = v.corroborators.map((c) => c.id);

  let campaignError: string | null = null;
  try {
    await insertCampaign({
      id: campaignId,
      intent: v.artifactPrompt,
      channel: v.targetChannel,
      status: "running",
      createdBy: v.operator,
      delayRangeSeconds: delayRange,
      roster,
      posts: [],
    });
  } catch (e) {
    campaignError = (e as Error).message.slice(0, 300);
  }

  // Either generate the image, or use the operator-uploaded one. In both
  // cases the post-processing chain (steg + EXIF transplant) runs and the
  // cascade per-corroborator perspective images render right after.
  try {
    if (uploadedImage) {
      await mkdir(GENERATED_DIR, { recursive: true });
      const outPath = path.join(GENERATED_DIR, `${v.missionId}.png`);
      await writeFile(outPath, new Uint8Array(uploadedImage.bytes));
      await spawnProcessUploadedArtifact(
        v.missionId,
        v.artifactPrompt,
        v.targetChannel,
        corroboratorIds,
      );
    } else {
      await spawnImageGen(
        v.missionId,
        v.artifactPrompt,
        v.targetChannel,
        corroboratorIds,
      );
    }
  } catch {
    // image step is best-effort; campaign still dispatches.
  }

  revalidatePath("/");
  revalidatePath("/audit");
  revalidatePath("/backstop");
  revalidatePath("/personas");
  return Response.json({
    ok: true,
    missionId: v.missionId,
    campaignId,
    inboxPath: finalPath,
    spec: v,
    campaignError,
  });
}
