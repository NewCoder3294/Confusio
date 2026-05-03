import "server-only";
import { readFile, writeFile, mkdir, rename } from "node:fs/promises";
import path from "node:path";

const REPO_ROOT = path.resolve(
  process.env.MENDACITY_REPO_ROOT ||
    path.join(process.env.HOME || "", "Mendacity"),
);
const ENV_PATH = path.join(REPO_ROOT, "social/config/api_credentials.env");

export const KNOWN_KEYS = [
  "OPENAI_API_KEY",
  "TELEGRAM_API_ID",
  "TELEGRAM_API_HASH",
  "OPERATOR_USER_ID",
] as const;

export type KnownKey = (typeof KNOWN_KEYS)[number];

export type SettingValue = {
  set: boolean;
  preview: string; // masked, e.g. "sk-•••abcd" or empty
};

export type SettingsSnapshot = Record<KnownKey, SettingValue>;

function mask(value: string): string {
  const v = value.trim();
  if (!v) return "";
  if (v.length <= 4) return "•".repeat(v.length);
  if (v.length <= 8) return v.slice(0, 1) + "•".repeat(v.length - 1);
  return v.slice(0, 4) + "•".repeat(Math.min(v.length - 8, 8)) + v.slice(-4);
}

/**
 * Parse a dotenv file into a key→value map. Tolerates blank lines and `#`
 * comments. Does not handle export-style declarations or multi-line values
 * — Mendacity's existing .env doesn't use them.
 */
function parseEnv(text: string): Map<string, string> {
  const out = new Map<string, string>();
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const eq = line.indexOf("=");
    if (eq < 0) continue;
    const key = line.slice(0, eq).trim();
    let val = line.slice(eq + 1).trim();
    // Strip optional surrounding quotes.
    if (
      (val.startsWith('"') && val.endsWith('"')) ||
      (val.startsWith("'") && val.endsWith("'"))
    ) {
      val = val.slice(1, -1);
    }
    out.set(key, val);
  }
  return out;
}

export async function readSettings(): Promise<SettingsSnapshot> {
  let text = "";
  try {
    text = await readFile(ENV_PATH, "utf-8");
  } catch {
    text = "";
  }
  const map = parseEnv(text);
  const snap = {} as SettingsSnapshot;
  for (const k of KNOWN_KEYS) {
    const v = (map.get(k) ?? "").trim();
    snap[k] = { set: v.length > 0, preview: mask(v) };
  }
  return snap;
}

/**
 * Update a key's value in place, preserving comments and ordering. Unknown
 * keys are appended at the bottom. Empty-string updates clear the value (set
 * to empty after the equals sign) but leave the line in place — same as the
 * existing file's "OPENAI_API_KEY=" style.
 *
 * Writes atomically: writes to a temp file, fsync via writeFile's default,
 * then renames into place.
 */
export async function updateSettings(
  updates: Partial<Record<KnownKey, string>>,
): Promise<void> {
  let text = "";
  try {
    text = await readFile(ENV_PATH, "utf-8");
  } catch {
    text = "# Mendacity secrets — gitignored. NEVER commit this file.\n";
  }

  const lines = text.split(/\r?\n/);
  const seen = new Set<string>();

  for (let i = 0; i < lines.length; i++) {
    const trimmed = lines[i].trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = trimmed.indexOf("=");
    if (eq < 0) continue;
    const key = trimmed.slice(0, eq).trim();
    if (Object.prototype.hasOwnProperty.call(updates, key)) {
      const v = updates[key as KnownKey] ?? "";
      lines[i] = `${key}=${v}`;
      seen.add(key);
    }
  }

  // Append any update keys that weren't present.
  const appended: string[] = [];
  for (const k of Object.keys(updates) as KnownKey[]) {
    if (seen.has(k)) continue;
    appended.push(`${k}=${updates[k] ?? ""}`);
  }
  if (appended.length > 0) {
    if (lines.length > 0 && lines[lines.length - 1].trim() !== "") {
      lines.push("");
    }
    lines.push(...appended);
  }

  // Ensure trailing newline.
  let out = lines.join("\n");
  if (!out.endsWith("\n")) out += "\n";

  await mkdir(path.dirname(ENV_PATH), { recursive: true });
  const tmp = path.join(
    path.dirname(ENV_PATH),
    `.api_credentials.env.${process.pid}.${Date.now()}.tmp`,
  );
  await writeFile(tmp, out, { encoding: "utf-8", mode: 0o600 });
  await rename(tmp, ENV_PATH);
  // The engine reloads .env on its next start; we don't signal it here.
}

export const ENV_FILE_PATH_FOR_DISPLAY = ENV_PATH;
