import "server-only";
import { spawn } from "node:child_process";
import path from "node:path";

const REPO_ROOT = path.resolve(
  process.env.MENDACITY_REPO_ROOT ||
    path.join(process.env.HOME || "", "Mendacity"),
);
const PYTHON =
  process.env.MENDACITY_PYTHON || path.join(REPO_ROOT, ".venv/bin/python");

export type TriageReport = {
  meta: {
    sha256?: string;
    mime_inferred?: string;
    size_bytes?: number;
    path?: string;
  };
  provenance: {
    c2pa?: {
      status: string;
      detail?: string;
      validation_state?: string;
      summary?: {
        claim_generator_info?: Array<{ name?: string; version?: string | null }>;
        actions?: unknown[];
      };
    };
    titan_watermark?: { status: string; [k: string]: unknown };
    google_synthid?: { status: string; [k: string]: unknown };
  };
  ai_surrogate: {
    model: string;
    backend: string;
    p_ai: number;
    p_real: number;
    raw_label?: string | null;
    note?: string | null;
  };
  exif: {
    fields: Record<string, string | number | boolean>;
    anomalies: string[];
    error?: string;
  };
  verdict: {
    label: "SUSPECTED_SYNTHETIC" | "INCONCLUSIVE" | "SUSPECTED_AUTHENTIC";
    confidence: "high" | "medium" | "low";
    score: number;
    drivers: string[];
  };
};

export async function runTriage(imagePath: string): Promise<TriageReport> {
  return new Promise((resolve, reject) => {
    const proc = spawn(
      PYTHON,
      ["-m", "forensic.triage", "--image", imagePath],
      {
        cwd: REPO_ROOT,
        env: { ...process.env, PYTHONPATH: path.join(REPO_ROOT, "src") },
      },
    );

    let stdout = "";
    let stderr = "";
    proc.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    proc.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    proc.on("error", reject);
    proc.on("close", (code) => {
      if (code !== 0) {
        reject(
          new Error(
            `forensic.triage exited ${code}: ${stderr.slice(0, 500) || "no stderr"}`,
          ),
        );
        return;
      }
      try {
        resolve(JSON.parse(stdout) as TriageReport);
      } catch (e) {
        reject(
          new Error(
            `Could not parse triage JSON: ${(e as Error).message}\nFirst 300 chars: ${stdout.slice(0, 300)}`,
          ),
        );
      }
    });
  });
}
