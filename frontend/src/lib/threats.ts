import "server-only";
import { mkdir, appendFile, readFile, stat } from "node:fs/promises";
import path from "node:path";
import crypto from "node:crypto";
import type { TriageReport } from "@/lib/triage";

const REPO_ROOT = path.resolve(
  process.env.MENDACITY_REPO_ROOT ||
    path.join(process.env.HOME || "", "Mendacity"),
);
const LIB_DIR = path.join(REPO_ROOT, "missions/threat-library");
const LIB_FILE = path.join(LIB_DIR, "triage-log.ndjson");

export type ThreatRecord = {
  id: string;
  receivedAt: string;
  filename: string;
  reviewer: string;
  report: TriageReport;
};

export async function appendThreatRecord(
  record: Omit<ThreatRecord, "id">,
): Promise<ThreatRecord> {
  await mkdir(LIB_DIR, { recursive: true });
  const id = `${Date.now()}-${crypto.randomBytes(4).toString("hex")}`;
  const full: ThreatRecord = { id, ...record };
  await appendFile(LIB_FILE, JSON.stringify(full) + "\n", "utf-8");
  return full;
}

export async function listThreatRecords(): Promise<ThreatRecord[]> {
  let raw: string;
  try {
    await stat(LIB_FILE);
    raw = await readFile(LIB_FILE, "utf-8");
  } catch {
    return [];
  }
  const out: ThreatRecord[] = [];
  for (const line of raw.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      out.push(JSON.parse(trimmed) as ThreatRecord);
    } catch {
      // skip malformed line
    }
  }
  // newest first
  return out.sort((a, b) => b.receivedAt.localeCompare(a.receivedAt));
}
