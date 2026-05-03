import "server-only";
import { stat } from "node:fs/promises";
import path from "node:path";
import { getDashboardSnapshot } from "@/lib/foundry";

const REPO_ROOT = path.resolve(
  process.env.MENDACITY_REPO_ROOT ||
    path.join(process.env.HOME || "", "Mendacity"),
);
const PERSONA_DB = path.join(REPO_ROOT, "social/mendacity.db");
const HEARTBEAT = path.join(REPO_ROOT, "social/.heartbeat");

export type SystemStatus = {
  foundry: { ok: boolean; missions: number; lastSyncIso: string | null; error?: string };
  engineDb: { ok: boolean; sizeBytes: number; mtimeIso: string | null; error?: string };
  bridge: { ok: boolean; lastBeatIso: string | null; secondsAgo: number | null };
  buildLabel: string;
  operator: string;
};

export async function getSystemStatus(): Promise<SystemStatus> {
  const buildLabel = process.env.MENDACITY_BUILD_LABEL || "BUILD v0.2 — DOSSIER";
  const operator = process.env.MENDACITY_OPERATOR || "J2-INSCOM-DEMO";

  const [foundry, engineDb, bridge] = await Promise.all([
    foundryStatus(),
    engineDbStatus(),
    bridgeStatus(),
  ]);

  return { foundry, engineDb, bridge, buildLabel, operator };
}

async function foundryStatus(): Promise<SystemStatus["foundry"]> {
  try {
    const snap = await getDashboardSnapshot();
    return {
      ok: true,
      missions: snap.missions.length,
      lastSyncIso: snap.fetchedAt,
    };
  } catch (e) {
    return {
      ok: false,
      missions: 0,
      lastSyncIso: null,
      error: (e as Error).message.slice(0, 200),
    };
  }
}

async function engineDbStatus(): Promise<SystemStatus["engineDb"]> {
  try {
    const info = await stat(PERSONA_DB);
    return {
      ok: info.isFile() && info.size > 0,
      sizeBytes: info.size,
      mtimeIso: info.mtime.toISOString(),
    };
  } catch (e) {
    return {
      ok: false,
      sizeBytes: 0,
      mtimeIso: null,
      error: (e as Error).message.slice(0, 200),
    };
  }
}

async function bridgeStatus(): Promise<SystemStatus["bridge"]> {
  try {
    const info = await stat(HEARTBEAT);
    const secondsAgo = (Date.now() - info.mtimeMs) / 1000;
    return {
      ok: secondsAgo < 60, // heartbeat older than 60s = bridge probably down
      lastBeatIso: info.mtime.toISOString(),
      secondsAgo,
    };
  } catch {
    return { ok: false, lastBeatIso: null, secondsAgo: null };
  }
}
