"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/* ─────────────────────────────────────────────────────────────────────── */
/* Types                                                                     */
/* ─────────────────────────────────────────────────────────────────────── */

interface DetectorSignal {
  detector: string;
  severity: "pass" | "warn" | "fail" | "n/a";
  score: number | null;
  evidence: string;
  latency_ms: number;
}

interface Verdict {
  level: "AUTHENTIC" | "SUSPECT" | "SYNTHETIC";
  confidence: number;
  summary: string;
}

interface VerifyResponse {
  artifact_id: string;
  sha256: string;
  verdict: Verdict;
  signals: DetectorSignal[];
  submitted_at: string;
  submitted_via: string;
  operator: string;
  thumbnail_uri: string | null;
}

interface HealthResponse {
  ok: boolean;
  classifier_warm: boolean;
  detectors: string[];
  audit_count: number;
}

interface RecentItem {
  ts: string;
  artifact_id: string;
  sha256: string;
  operator: string;
  source: string;
  verdict_level: string;
  verdict_confidence: number;
  verdict_summary: string;
}

interface SessionEntry {
  artifactId: string;
  sha256Prefix: string;
  verdictLevel: Verdict["level"];
  response: VerifyResponse;
  dataUrl: string;
  fileName: string;
  fileSize: number;
  mimeType: string;
}

type DetectorState =
  | { phase: "ready" }
  | { phase: "running" }
  | { phase: "done"; signal: DetectorSignal };

/* ─────────────────────────────────────────────────────────────────────── */
/* Constants                                                                 */
/* ─────────────────────────────────────────────────────────────────────── */

const DETECTOR_LABELS: Record<string, string> = {
  c2pa: "C2PA",
  gemini_visual: "GEMINI",
  ai_classifier: "AI-GEN",
  exif: "EXIF",
  ela: "ELA",
  phash: "PHASH",
  titan: "TITAN",
};

const DETECTOR_ORDER = ["c2pa", "gemini_visual", "ai_classifier", "exif", "ela", "phash", "titan"];

/* ─────────────────────────────────────────────────────────────────────── */
/* Severity / verdict inline styles                                          */
/* ─────────────────────────────────────────────────────────────────────── */

const SV_PASS: React.CSSProperties = { background: "#16271c", border: "1px solid #2d5a3a", color: "#9be0a8" };
const SV_WARN: React.CSSProperties = { background: "#2e2410", border: "1px solid #6b4f1c", color: "#ffd591" };
const SV_FAIL: React.CSSProperties = { background: "#3a1f1f", border: "1px solid #6e2b2b", color: "#ffb4b4" };
const SV_NA:   React.CSSProperties = { background: "#1a1f26", border: "1px solid #3a4048", color: "#9aa0a6" };
const SV_READY: React.CSSProperties = { background: "#11151a", border: "1px solid #2a2f36", color: "#7a8088" };
const SV_RUNNING: React.CSSProperties = { background: "#2e2410", border: "1px solid #6b4f1c", color: "#ffd591" };

function severityStyle(sev: DetectorSignal["severity"]): React.CSSProperties {
  if (sev === "pass") return SV_PASS;
  if (sev === "warn") return SV_WARN;
  if (sev === "fail") return SV_FAIL;
  return SV_NA;
}

const VERDICT_PILL: Record<string, React.CSSProperties> = {
  AUTHENTIC: SV_PASS,
  SUSPECT: SV_WARN,
  SYNTHETIC: SV_FAIL,
};

/* ─────────────────────────────────────────────────────────────────────── */
/* Helpers                                                                   */
/* ─────────────────────────────────────────────────────────────────────── */

function relativeTime(iso: string): string {
  try {
    const diff = Date.now() - new Date(iso).getTime();
    const sec = Math.floor(diff / 1000);
    if (sec < 60) return `${sec}s ago`;
    const min = Math.floor(sec / 60);
    if (min < 60) return `${min}m ago`;
    const hr = Math.floor(min / 60);
    return `${hr}h ago`;
  } catch {
    return "—";
  }
}

function tsZulu(iso: string): string {
  try {
    return new Date(iso).toISOString().slice(11, 19) + "Z";
  } catch {
    return "—";
  }
}

/* ─────────────────────────────────────────────────────────────────────── */
/* Status Bar                                                                */
/* ─────────────────────────────────────────────────────────────────────── */

function StatusBar({
  health,
  reachable,
  lastVerdict,
}: {
  health: HealthResponse | null;
  reachable: boolean;
  lastVerdict: RecentItem | null;
}) {
  const dotColor = !reachable
    ? "#e36b6b"
    : health?.classifier_warm
    ? "#6cd690"
    : "#e3b14a";

  const dotLabel = !reachable
    ? "API unreachable"
    : `API live · 127.0.0.1:3001`;

  const engineLabel = !reachable
    ? "Engine offline"
    : health?.classifier_warm
    ? "Engine warm"
    : "Engine cold";

  const detectorCount = health?.detectors.length ?? 0;
  const detectorsLabel = `${detectorCount}/7 detectors ready`;

  return (
    <div
      style={{
        borderBottom: "1px solid var(--border-subtle, #232830)",
        background: "var(--bg-elevated, #181c21)",
        fontFamily: "var(--font-geist-mono), ui-monospace, monospace",
        fontSize: "11px",
        color: "var(--fg-muted, #9aa3ad)",
      }}
    >
      {/* Top row: brand + title */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "8px 16px 6px",
          borderBottom: "1px solid var(--border-subtle, #232830)",
        }}
      >
        <span
          style={{
            fontSize: "10px",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            color: "var(--fg-faint, #6b7480)",
          }}
        >
          Defensive Arm · Counter-Deception
        </span>
        <span
          style={{
            fontSize: "13px",
            letterSpacing: "0.22em",
            textTransform: "uppercase",
            color: "var(--classified, #e05252)",
            fontWeight: 600,
          }}
        >
          VERIFY
        </span>
      </div>

      {/* Status pills row */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "20px",
          padding: "6px 16px",
          flexWrap: "wrap",
        }}
      >
        <span style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <span
            style={{
              width: "7px",
              height: "7px",
              borderRadius: "50%",
              background: dotColor,
              display: "inline-block",
              flexShrink: 0,
            }}
          />
          <span style={{ color: "var(--fg-default, #e6e9ec)" }}>{dotLabel}</span>
        </span>

        {reachable && (
          <>
            <span style={{ display: "flex", alignItems: "center", gap: "6px" }}>
              <span
                style={{
                  width: "7px",
                  height: "7px",
                  borderRadius: "50%",
                  background: health?.classifier_warm ? "#6cd690" : "#e3b14a",
                  display: "inline-block",
                  flexShrink: 0,
                }}
              />
              <span>{engineLabel}</span>
            </span>

            <span style={{ display: "flex", alignItems: "center", gap: "6px" }}>
              <span
                style={{
                  width: "7px",
                  height: "7px",
                  borderRadius: "50%",
                  background: detectorCount === 7 ? "#6cd690" : "#e3b14a",
                  display: "inline-block",
                  flexShrink: 0,
                }}
              />
              <span>{detectorsLabel}</span>
            </span>
          </>
        )}

        {lastVerdict && (
          <span
            style={{
              marginLeft: "auto",
              color: "var(--fg-faint, #6b7480)",
              fontSize: "10px",
              letterSpacing: "0.1em",
            }}
          >
            Last verdict:{" "}
            <span style={{ color: "var(--fg-mono, #c4cad1)" }}>
              {lastVerdict.sha256.slice(0, 4)}…{lastVerdict.sha256.slice(-4)}
            </span>{" "}
            <span
              style={{
                ...VERDICT_PILL[lastVerdict.verdict_level] ?? SV_NA,
                padding: "1px 6px",
                fontSize: "9px",
                letterSpacing: "0.14em",
                textTransform: "uppercase",
              }}
            >
              {lastVerdict.verdict_level}
            </span>{" "}
            <span>{tsZulu(lastVerdict.ts)}</span>
          </span>
        )}
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────── */
/* Activity Sidebar                                                          */
/* ─────────────────────────────────────────────────────────────────────── */

function ActivitySidebar({
  items,
  sessionEntries,
  onSelectAuditItem,
  onSelectSessionEntry,
  activeArtifactId,
}: {
  items: RecentItem[];
  sessionEntries: SessionEntry[];
  onSelectAuditItem: (item: RecentItem) => void;
  onSelectSessionEntry: (entry: SessionEntry) => void;
  activeArtifactId: string | null;
}) {
  return (
    <aside
      style={{
        borderRight: "1px solid var(--border-subtle, #232830)",
        background: "var(--bg-panel, #111418)",
        display: "flex",
        flexDirection: "column",
        overflowY: "auto",
        minWidth: 0,
      }}
    >
      <div
        style={{
          padding: "7px 12px 6px",
          borderBottom: "1px solid var(--border-subtle, #232830)",
          background: "var(--bg-elevated, #181c21)",
          fontFamily: "var(--font-geist-mono), ui-monospace, monospace",
          fontSize: "10px",
          letterSpacing: "0.16em",
          textTransform: "uppercase",
          color: "var(--fg-faint, #6b7480)",
          flexShrink: 0,
        }}
      >
        Activity
      </div>

      {/* Current session entries first */}
      {sessionEntries.map((e) => {
        const isActive = e.artifactId === activeArtifactId;
        return (
          <button
            key={e.artifactId}
            onClick={() => onSelectSessionEntry(e)}
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "2px",
              padding: "7px 10px",
              borderBottom: "1px solid var(--border-subtle, #232830)",
              background: isActive ? "var(--bg-elevated, #181c21)" : "transparent",
              borderLeft: isActive ? "2px solid #5fb8d6" : "2px solid transparent",
              cursor: "pointer",
              width: "100%",
              textAlign: "left",
              fontFamily: "var(--font-geist-mono), ui-monospace, monospace",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "6px" }}>
              <span style={{ fontSize: "10px", color: "var(--fg-mono, #c4cad1)" }}>
                {e.sha256Prefix}
              </span>
              <span
                style={{
                  ...VERDICT_PILL[e.verdictLevel] ?? SV_NA,
                  fontSize: "9px",
                  letterSpacing: "0.12em",
                  textTransform: "uppercase",
                  padding: "1px 5px",
                  flexShrink: 0,
                }}
              >
                {e.verdictLevel}
              </span>
            </div>
            <div style={{ display: "flex", gap: "6px", fontSize: "9px", color: "var(--fg-faint, #6b7480)" }}>
              <span>verify_tab</span>
              <span>·</span>
              <span style={{ color: "#5fb8d6" }}>this session</span>
            </div>
          </button>
        );
      })}

      {/* Audit feed from API */}
      {items.length === 0 && sessionEntries.length === 0 ? (
        <div
          style={{
            padding: "16px 10px",
            fontFamily: "var(--font-geist-sans), system-ui, sans-serif",
            fontSize: "11px",
            color: "var(--fg-faint, #6b7480)",
            fontStyle: "italic",
          }}
        >
          No verifications yet system-wide.
        </div>
      ) : (
        items
          .filter((item) => !sessionEntries.some((e) => e.artifactId === item.artifact_id))
          .map((item) => {
            const isActive = item.artifact_id === activeArtifactId;
            return (
              <button
                key={item.artifact_id}
                onClick={() => onSelectAuditItem(item)}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "2px",
                  padding: "7px 10px",
                  borderBottom: "1px solid var(--border-subtle, #232830)",
                  background: isActive ? "var(--bg-elevated, #181c21)" : "transparent",
                  borderLeft: isActive ? "2px solid #5fb8d6" : "2px solid transparent",
                  cursor: "pointer",
                  width: "100%",
                  textAlign: "left",
                  fontFamily: "var(--font-geist-mono), ui-monospace, monospace",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "6px" }}>
                  <span style={{ fontSize: "10px", color: "var(--fg-mono, #c4cad1)" }}>
                    {item.sha256.slice(0, 8)}
                  </span>
                  <span
                    style={{
                      ...VERDICT_PILL[item.verdict_level] ?? SV_NA,
                      fontSize: "9px",
                      letterSpacing: "0.12em",
                      textTransform: "uppercase",
                      padding: "1px 5px",
                      flexShrink: 0,
                    }}
                  >
                    {item.verdict_level}
                  </span>
                </div>
                <div style={{ display: "flex", gap: "6px", fontSize: "9px", color: "var(--fg-faint, #6b7480)" }}>
                  <span>{relativeTime(item.ts)}</span>
                  <span>·</span>
                  <span>{item.source}</span>
                </div>
              </button>
            );
          })
      )}
    </aside>
  );
}

/* ─────────────────────────────────────────────────────────────────────── */
/* Detector Grid                                                             */
/* ─────────────────────────────────────────────────────────────────────── */

function DetectorGrid({ states }: { states: Record<string, DetectorState> }) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "6px",
        padding: "10px",
      }}
    >
      {DETECTOR_ORDER.map((key) => {
        const state = states[key] ?? { phase: "ready" };
        const label = DETECTOR_LABELS[key] ?? key.toUpperCase();

        let cellStyle: React.CSSProperties;
        let badgeStyle: React.CSSProperties;
        let badgeText: string;
        let evidenceText: string | null = null;

        if (state.phase === "ready") {
          cellStyle = { ...SV_READY, padding: "8px 10px", display: "flex", flexDirection: "column", gap: "4px" };
          badgeStyle = { ...SV_READY, fontSize: "9px", letterSpacing: "0.14em", padding: "1px 6px", textTransform: "uppercase" as const };
          badgeText = "READY";
        } else if (state.phase === "running") {
          cellStyle = { ...SV_RUNNING, padding: "8px 10px", display: "flex", flexDirection: "column", gap: "4px" };
          badgeStyle = { ...SV_RUNNING, fontSize: "9px", letterSpacing: "0.14em", padding: "1px 6px", textTransform: "uppercase" as const };
          badgeText = "RUNNING…";
        } else {
          const sig = state.signal;
          const base = severityStyle(sig.severity);
          cellStyle = { ...base, padding: "8px 10px", display: "flex", flexDirection: "column", gap: "4px" };
          badgeStyle = { ...base, fontSize: "9px", letterSpacing: "0.14em", padding: "1px 6px", textTransform: "uppercase" as const };
          badgeText = sig.severity === "n/a" ? "N/A" : sig.severity.toUpperCase();
          evidenceText = sig.severity === "n/a" ? "unavailable" : sig.evidence;
        }

        return (
          <div
            key={key}
            style={{
              ...cellStyle,
              animation: state.phase === "running" ? "pulse 1.2s ease-in-out infinite" : undefined,
            }}
          >
            {/* Name + badge on one row */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "8px" }}>
              <span
                style={{
                  fontFamily: "var(--font-geist-mono), ui-monospace, monospace",
                  fontSize: "10px",
                  letterSpacing: "0.16em",
                  textTransform: "uppercase",
                  color: cellStyle.color as string,
                  opacity: 0.85,
                }}
              >
                {label}
              </span>
              <span style={{ ...badgeStyle, flexShrink: 0 }}>{badgeText}</span>
            </div>
            {/* Evidence below, full width */}
            {evidenceText && (
              <span
                style={{
                  fontFamily: "var(--font-geist-mono), ui-monospace, monospace",
                  fontSize: "9px",
                  color: cellStyle.color as string,
                  opacity: 0.7,
                  wordBreak: "break-all",
                  lineHeight: "1.4",
                }}
              >
                {evidenceText}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────── */
/* Drop Zone + Sample Buttons                                                */
/* ─────────────────────────────────────────────────────────────────────── */

const SAMPLES = [
  { key: "iphone", label: "iPhone (real)", path: "/samples/iphone.jpg", mime: "image/jpeg" },
  { key: "dalle", label: "DALL-E (synthetic)", path: "/samples/dalle.jpg", mime: "image/jpeg" },
  { key: "gemini", label: "Gemini (synthetic)", path: "/samples/gemini.png", mime: "image/png" },
];

function DropZonePanel({
  onFile,
  isLoading,
  error,
}: {
  onFile: (file: File) => void;
  isLoading: boolean;
  error: { code: string; message: string } | null;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback(() => setIsDragging(false), []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) onFile(file);
    },
    [onFile],
  );

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) onFile(file);
    },
    [onFile],
  );

  const loadSample = useCallback(
    async (path: string, mime: string, label: string) => {
      try {
        const res = await fetch(path);
        const blob = await res.blob();
        const ext = path.split(".").pop() ?? "jpg";
        const file = new File([blob], `sample-${label}.${ext}`, { type: mime });
        onFile(file);
      } catch {
        // ignore
      }
    },
    [onFile],
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: "1", minHeight: "0", padding: "12px", gap: "10px" }}>
      {/* Error banner */}
      {error && (
        <div
          style={{
            background: "#2a1212",
            border: "1px solid #4a1f1f",
            color: "#e36b6b",
            padding: "8px 12px",
            fontFamily: "var(--font-geist-mono), ui-monospace, monospace",
            fontSize: "11px",
            letterSpacing: "0.1em",
            flexShrink: 0,
          }}
        >
          <span style={{ textTransform: "uppercase", letterSpacing: "0.14em" }}>
            {error.code}
          </span>{" "}
          — {error.message}
        </div>
      )}

      {/* Sample buttons — shown above the drop zone */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "6px",
          flexShrink: 0,
        }}
      >
        <div
          style={{
            fontFamily: "var(--font-geist-mono), ui-monospace, monospace",
            fontSize: "9px",
            letterSpacing: "0.16em",
            textTransform: "uppercase",
            color: "var(--fg-faint, #6b7480)",
            marginBottom: "2px",
          }}
        >
          TRY:
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
          {SAMPLES.map((s) => (
            <button
              key={s.key}
              disabled={isLoading}
              onClick={() => loadSample(s.path, s.mime, s.label)}
              style={{
                fontFamily: "var(--font-geist-mono), ui-monospace, monospace",
                fontSize: "10px",
                letterSpacing: "0.12em",
                background: "transparent",
                border: "1px solid var(--border-default, #2c333c)",
                color: isLoading ? "var(--fg-faint, #6b7480)" : "var(--fg-muted, #9aa3ad)",
                padding: "4px 10px",
                cursor: isLoading ? "not-allowed" : "pointer",
                transition: "color 0.1s, border-color 0.1s",
              }}
              onMouseEnter={(e) => {
                if (!isLoading) {
                  (e.currentTarget as HTMLButtonElement).style.color = "var(--fg-default, #e6e9ec)";
                  (e.currentTarget as HTMLButtonElement).style.borderColor = "#5fb8d6";
                }
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.color = "var(--fg-muted, #9aa3ad)";
                (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--border-default, #2c333c)";
              }}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      {/* Drop zone — fills remaining vertical space */}
      <div
        role="button"
        tabIndex={0}
        aria-label="Drop image here or click to choose file"
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => !isLoading && inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            if (!isLoading) inputRef.current?.click();
          }
        }}
        style={{
          border: `1px dashed ${isDragging ? "#5fb8d6" : "var(--border-default, #2c333c)"}`,
          background: isDragging ? "#0e2530" : "var(--bg-panel, #111418)",
          padding: "36px 24px",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: "8px",
          cursor: isLoading ? "wait" : "pointer",
          transition: "border-color 0.15s, background 0.15s",
          flex: "1",
          minHeight: "0",
        }}
      >
        {isLoading ? (
          <>
            <span
              style={{
                fontFamily: "var(--font-geist-mono), ui-monospace, monospace",
                fontSize: "12px",
                color: "var(--fg-muted, #9aa3ad)",
                letterSpacing: "0.1em",
              }}
            >
              Verifying…
            </span>
            <span
              style={{
                fontSize: "11px",
                color: "var(--fg-faint, #6b7480)",
                fontFamily: "var(--font-geist-sans), system-ui, sans-serif",
              }}
            >
              Running 8 detectors
            </span>
          </>
        ) : (
          <>
            <span
              style={{
                fontFamily: "var(--font-geist-mono), ui-monospace, monospace",
                fontSize: "12px",
                color: "var(--fg-muted, #9aa3ad)",
                letterSpacing: "0.1em",
              }}
            >
              Drop image to verify
            </span>
            <span
              style={{
                fontSize: "11px",
                color: "var(--fg-faint, #6b7480)",
                fontFamily: "var(--font-geist-sans), system-ui, sans-serif",
              }}
            >
              JPEG / PNG / WebP · 10 MB max
            </span>
          </>
        )}
      </div>

      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        style={{ display: "none" }}
        onChange={handleChange}
      />
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────── */
/* Dossier                                                                   */
/* ─────────────────────────────────────────────────────────────────────── */

function Dossier({
  entry,
  onVerifyAnother,
}: {
  entry: SessionEntry;
  onVerifyAnother: () => void;
}) {
  const { response, dataUrl, fileName, fileSize, mimeType } = entry;
  const { verdict, signals, submitted_at, operator, sha256 } = response;

  const verdictPill = VERDICT_PILL[verdict.level] ?? SV_NA;

  const provenance = signals.filter((s) => ["c2pa", "synthid", "titan"].includes(s.detector));
  const synthesis = signals.filter((s) => ["ai_classifier", "exif"].includes(s.detector));
  const tamper = signals.filter((s) => ["ela", "phash"].includes(s.detector));

  function provenanceConclusion(sigs: DetectorSignal[]): string {
    const fails = sigs.filter((s) => s.severity === "fail");
    const passes = sigs.filter((s) => s.severity === "pass");
    if (fails.length > 0) return `Provenance chain compromised: ${fails.map((s) => s.detector).join(", ")} indicate manipulation.`;
    if (passes.length > 0) return "Provenance chain intact across checked detectors.";
    return "No provenance signals detected — absence expected for unembedded imagery.";
  }

  function synthesisConclusion(sigs: DetectorSignal[]): string {
    const fails = sigs.filter((s) => s.severity === "fail");
    if (fails.length > 0) return `Synthesis indicators positive: ${fails.map((s) => s.evidence).join("; ")}.`;
    return "No synthesis indicators detected.";
  }

  function tamperConclusion(sigs: DetectorSignal[]): string {
    const fails = sigs.filter((s) => s.severity === "fail");
    if (fails.length > 0) return `Tamper evidence detected: ${fails.map((s) => s.evidence).join("; ")}.`;
    return "No tamper evidence detected. ELA and perceptual hash within nominal bounds.";
  }

  const SEV_COLOR: Record<DetectorSignal["severity"], string> = {
    pass: "#6cd690",
    warn: "#e3b14a",
    fail: "#e36b6b",
    "n/a": "#6b7480",
  };

  return (
    <div
      style={{
        fontFamily: "var(--font-geist-mono), ui-monospace, monospace",
        fontSize: "12px",
        color: "var(--fg-default, #e6e9ec)",
      }}
    >
      {/* Back button */}
      <div
        style={{
          padding: "8px 14px",
          borderBottom: "1px solid var(--border-subtle, #232830)",
          display: "flex",
          alignItems: "center",
          gap: "10px",
        }}
      >
        <button
          onClick={onVerifyAnother}
          style={{
            fontFamily: "inherit",
            fontSize: "10px",
            letterSpacing: "0.14em",
            textTransform: "uppercase",
            background: "transparent",
            border: "1px solid var(--border-default, #2c333c)",
            color: "var(--fg-muted, #9aa3ad)",
            padding: "3px 10px",
            cursor: "pointer",
          }}
          onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.color = "#e6e9ec"; }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.color = "var(--fg-muted, #9aa3ad)"; }}
        >
          ← Back
        </button>
        <span style={{ fontSize: "10px", color: "var(--fg-faint, #6b7480)", letterSpacing: "0.12em", textTransform: "uppercase" }}>
          Dossier · {new Date(submitted_at).toISOString()} · {operator}
        </span>
      </div>

      {/* Subject */}
      <div
        style={{
          padding: "10px 14px",
          borderBottom: "1px solid var(--border-subtle, #232830)",
          display: "flex",
          gap: "14px",
          alignItems: "flex-start",
        }}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={dataUrl}
          alt="Subject"
          style={{ width: "80px", height: "54px", objectFit: "cover", border: "1px solid var(--border-default, #2c333c)", flexShrink: 0 }}
        />
        <div style={{ display: "grid", gridTemplateColumns: "80px 1fr", gap: "3px 8px", fontSize: "10px" }}>
          {[
            ["FILE", fileName],
            ["SHA256", sha256.slice(0, 32) + "…"],
            ["MIME", mimeType],
            ["BYTES", fileSize.toLocaleString()],
          ].map(([l, v]) => (
            <>
              <span key={`l-${l}`} style={{ color: "var(--fg-faint, #6b7480)", textTransform: "uppercase", letterSpacing: "0.1em", fontSize: "9px" }}>{l}</span>
              <span key={`v-${l}`} style={{ color: "var(--fg-mono, #c4cad1)" }}>{v}</span>
            </>
          ))}
        </div>
      </div>

      {/* Sections */}
      {[
        { heading: "§1 Provenance", sigs: provenance, conclusion: provenanceConclusion(provenance) },
        { heading: "§2 Synthesis Indicators", sigs: synthesis, conclusion: synthesisConclusion(synthesis) },
        { heading: "§3 Tamper Evidence", sigs: tamper, conclusion: tamperConclusion(tamper) },
      ].map(({ heading, sigs, conclusion }) => (
        <div key={heading} style={{ borderBottom: "1px solid var(--border-subtle, #232830)", padding: "10px 14px" }}>
          <div style={{ fontSize: "9px", letterSpacing: "0.16em", textTransform: "uppercase", color: "var(--fg-faint, #6b7480)", marginBottom: "7px" }}>
            {heading}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "3px", marginBottom: "8px" }}>
            {sigs.map((s) => (
              <div key={s.detector} style={{ display: "flex", gap: "10px", alignItems: "baseline" }}>
                <span style={{ fontSize: "10px", color: "var(--fg-muted, #9aa3ad)", minWidth: "84px", textTransform: "uppercase", letterSpacing: "0.1em" }}>
                  {s.detector}
                </span>
                <span style={{ color: SEV_COLOR[s.severity], fontSize: "9px", letterSpacing: "0.12em", textTransform: "uppercase", minWidth: "34px" }}>
                  {s.severity}
                </span>
                <span style={{ color: "var(--fg-muted, #9aa3ad)", fontSize: "10px" }}>
                  {s.severity === "n/a" ? "detector unavailable" : s.evidence}
                </span>
              </div>
            ))}
          </div>
          <p style={{ fontFamily: "var(--font-geist-sans), system-ui, sans-serif", fontSize: "11px", color: "var(--fg-muted, #9aa3ad)", lineHeight: "1.6", margin: 0 }}>
            {conclusion}
          </p>
        </div>
      ))}

      {/* Verdict footer */}
      <div
        style={{
          padding: "10px 14px",
          background: "var(--bg-elevated, #181c21)",
          display: "flex",
          alignItems: "center",
          gap: "14px",
          flexWrap: "wrap",
        }}
      >
        <span style={{ ...verdictPill, padding: "3px 10px", fontSize: "10px", letterSpacing: "0.18em", textTransform: "uppercase" }}>
          {verdict.level}
        </span>
        <span style={{ color: "var(--fg-faint, #6b7480)", fontSize: "10px" }}>
          confidence{" "}
          <span style={{ color: "var(--fg-mono, #c4cad1)" }}>{verdict.confidence.toFixed(2)}</span>
        </span>
        <span style={{ color: "var(--fg-muted, #9aa3ad)", fontSize: "11px", fontFamily: "var(--font-geist-sans), system-ui, sans-serif", flex: 1 }}>
          {verdict.summary}
        </span>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────── */
/* Page                                                                      */
/* ─────────────────────────────────────────────────────────────────────── */

export default function VerifyPage() {
  // Health / recent state
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [reachable, setReachable] = useState(true);
  const [recentItems, setRecentItems] = useState<RecentItem[]>([]);

  // Verify state
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<{ code: string; message: string } | null>(null);
  const [detectorStates, setDetectorStates] = useState<Record<string, DetectorState>>(
    Object.fromEntries(DETECTOR_ORDER.map((k) => [k, { phase: "ready" }])),
  );

  // Session / active dossier
  const [session, setSession] = useState<SessionEntry[]>([]);
  const [activeEntry, setActiveEntry] = useState<SessionEntry | null>(null);
  const [activeAuditItem, setActiveAuditItem] = useState<RecentItem | null>(null);

  // Poll health
  const fetchHealth = useCallback(async () => {
    try {
      const res = await fetch("/api/verify/health", { cache: "no-store" });
      if (res.ok) {
        const data = (await res.json()) as HealthResponse;
        setHealth(data);
        setReachable(true);
      } else {
        setReachable(false);
      }
    } catch {
      setReachable(false);
    }
  }, []);

  // Poll recent
  const fetchRecent = useCallback(async () => {
    try {
      const res = await fetch("/api/verify/recent", { cache: "no-store" });
      if (res.ok) {
        const data = (await res.json()) as { items: RecentItem[] };
        setRecentItems(data.items);
      }
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    fetchHealth();
    fetchRecent();
    const healthTimer = setInterval(fetchHealth, 30_000);
    const recentTimer = setInterval(fetchRecent, 15_000);
    return () => {
      clearInterval(healthTimer);
      clearInterval(recentTimer);
    };
  }, [fetchHealth, fetchRecent]);

  // Handle file verify
  const handleFile = useCallback(
    async (file: File) => {
      setIsLoading(true);
      setError(null);
      setActiveEntry(null);
      setActiveAuditItem(null);

      // Set all detectors to RUNNING
      setDetectorStates(Object.fromEntries(DETECTOR_ORDER.map((k) => [k, { phase: "running" }])));

      const dataUrl = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result as string);
        reader.onerror = () => reject(new Error("Failed to read file"));
        reader.readAsDataURL(file);
      });

      const form = new FormData();
      form.append("image", file);

      let data: VerifyResponse;
      try {
        const res = await fetch("/api/verify", { method: "POST", body: form });

        if (!res.ok) {
          let code = "api_error";
          let message = `HTTP ${res.status}`;
          try {
            const json = (await res.json()) as {
              detail?: { code?: string; error?: string } | string;
            };
            if (typeof json.detail === "object" && json.detail !== null) {
              code = json.detail.code ?? code;
              message = json.detail.error ?? message;
            } else if (typeof json.detail === "string") {
              message = json.detail;
            }
          } catch {
            // keep defaults
          }
          setError({ code, message });
          setDetectorStates(Object.fromEntries(DETECTOR_ORDER.map((k) => [k, { phase: "ready" }])));
          setIsLoading(false);
          return;
        }

        data = (await res.json()) as VerifyResponse;
      } catch (err) {
        setError({
          code: "network_error",
          message: err instanceof Error ? err.message : String(err),
        });
        setDetectorStates(Object.fromEntries(DETECTOR_ORDER.map((k) => [k, { phase: "ready" }])));
        setIsLoading(false);
        return;
      }

      // Update detector states with results
      const newStates: Record<string, DetectorState> = {};
      for (const key of DETECTOR_ORDER) {
        const sig = data.signals.find((s) => s.detector === key);
        if (sig) {
          newStates[key] = { phase: "done", signal: sig };
        } else {
          newStates[key] = {
            phase: "done",
            signal: { detector: key, severity: "n/a", score: null, evidence: "not run", latency_ms: 0 },
          };
        }
      }
      setDetectorStates(newStates);

      const entry: SessionEntry = {
        artifactId: data.artifact_id,
        sha256Prefix: data.sha256.slice(0, 8),
        verdictLevel: data.verdict.level,
        response: data,
        dataUrl,
        fileName: file.name,
        fileSize: file.size,
        mimeType: file.type,
      };

      setSession((prev) => [entry, ...prev]);
      setActiveEntry(entry);
      setIsLoading(false);

      // Refresh activity feed after verify
      fetchRecent();
    },
    [fetchRecent],
  );

  const handleVerifyAnother = useCallback(() => {
    setActiveEntry(null);
    setActiveAuditItem(null);
    setError(null);
    setDetectorStates(Object.fromEntries(DETECTOR_ORDER.map((k) => [k, { phase: "ready" }])));
  }, []);

  const handleSelectAuditItem = useCallback(async (item: RecentItem) => {
    // Try to fetch full response from in-process cache via proxy
    setActiveAuditItem(item);
    setActiveEntry(null);
    // We can only show cached data for session entries; for cross-session items
    // we show a read-only summary view (see below)
  }, []);

  const handleSelectSessionEntry = useCallback((entry: SessionEntry) => {
    setActiveEntry(entry);
    setActiveAuditItem(null);
  }, []);

  // The active artifact ID for sidebar highlighting
  const activeArtifactId =
    activeEntry?.artifactId ?? activeAuditItem?.artifact_id ?? null;

  // Determine what to show in the main area
  const showDossier = activeEntry !== null;
  const showAuditReadOnly = !showDossier && activeAuditItem !== null;
  const showDropZone = !showDossier && !showAuditReadOnly;

  return (
    <>
      {/* Pulse keyframe injected once */}
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.45; }
        }
      `}</style>

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          flex: "1",
          minHeight: "0",
          overflow: "hidden",
        }}
      >
        {/* Status bar */}
        <StatusBar
          health={health}
          reachable={reachable}
          lastVerdict={recentItems[0] ?? null}
        />

        {/* Three-column layout */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "180px 1fr 300px",
            flex: "1",
            minHeight: "0",
            overflow: "hidden",
          }}
        >
          {/* Left: Activity */}
          <ActivitySidebar
            items={recentItems}
            sessionEntries={session}
            onSelectAuditItem={handleSelectAuditItem}
            onSelectSessionEntry={handleSelectSessionEntry}
            activeArtifactId={activeArtifactId}
          />

          {/* Centre: Drop zone or Dossier */}
          <main
            style={{
              display: "flex",
              flexDirection: "column",
              height: "100%",
              minHeight: "0",
              background: "var(--bg-base, #0a0c0e)",
              borderRight: "1px solid var(--border-subtle, #232830)",
              overflow: "hidden",
            }}
          >
            {showDossier && activeEntry ? (
              <div
                style={{
                  border: "1px solid var(--border-default, #2c333c)",
                  margin: "12px",
                  background: "var(--bg-panel, #111418)",
                  flex: "1",
                  minHeight: "0",
                  overflowY: "auto",
                }}
              >
                <Dossier entry={activeEntry} onVerifyAnother={handleVerifyAnother} />
              </div>
            ) : showAuditReadOnly && activeAuditItem ? (
              <div
                style={{
                  margin: "12px",
                  border: "1px solid var(--border-default, #2c333c)",
                  background: "var(--bg-panel, #111418)",
                  fontFamily: "var(--font-geist-mono), ui-monospace, monospace",
                  fontSize: "11px",
                  color: "var(--fg-default, #e6e9ec)",
                  flex: "1",
                  minHeight: "0",
                  overflowY: "auto",
                }}
              >
                <div style={{ padding: "8px 14px", borderBottom: "1px solid var(--border-subtle, #232830)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: "10px", color: "var(--fg-faint, #6b7480)", letterSpacing: "0.12em", textTransform: "uppercase" }}>
                    Audit Record · {activeAuditItem.artifact_id.slice(0, 8)}…
                  </span>
                  <button
                    onClick={handleVerifyAnother}
                    style={{ fontFamily: "inherit", fontSize: "10px", letterSpacing: "0.14em", textTransform: "uppercase", background: "transparent", border: "1px solid var(--border-default, #2c333c)", color: "var(--fg-muted, #9aa3ad)", padding: "3px 10px", cursor: "pointer" }}
                    onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.color = "#e6e9ec"; }}
                    onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.color = "var(--fg-muted, #9aa3ad)"; }}
                  >
                    ← Back
                  </button>
                </div>
                <div style={{ padding: "12px 14px", display: "grid", gridTemplateColumns: "90px 1fr", gap: "5px 10px", fontSize: "10px" }}>
                  {[
                    ["TIME", new Date(activeAuditItem.ts).toISOString()],
                    ["SHA256", activeAuditItem.sha256.slice(0, 32) + "…"],
                    ["OPERATOR", activeAuditItem.operator],
                    ["SOURCE", activeAuditItem.source],
                    ["VERDICT", activeAuditItem.verdict_level],
                    ["CONFIDENCE", activeAuditItem.verdict_confidence.toFixed(2)],
                    ["SUMMARY", activeAuditItem.verdict_summary],
                  ].map(([l, v]) => (
                    <>
                      <span key={`l-${l}`} style={{ color: "var(--fg-faint, #6b7480)", textTransform: "uppercase", letterSpacing: "0.1em", fontSize: "9px" }}>{l}</span>
                      <span key={`v-${l}`} style={{ color: "var(--fg-mono, #c4cad1)" }}>{v}</span>
                    </>
                  ))}
                </div>
                <div style={{ padding: "10px 14px", borderTop: "1px solid var(--border-subtle, #232830)" }}>
                  <span
                    style={{
                      ...VERDICT_PILL[activeAuditItem.verdict_level] ?? SV_NA,
                      padding: "3px 10px",
                      fontSize: "10px",
                      letterSpacing: "0.18em",
                      textTransform: "uppercase",
                    }}
                  >
                    {activeAuditItem.verdict_level}
                  </span>
                  <span style={{ fontSize: "11px", color: "var(--fg-faint, #6b7480)", marginLeft: "12px", fontFamily: "var(--font-geist-sans), system-ui, sans-serif" }}>
                    Full dossier only available for images verified this session.
                  </span>
                </div>
              </div>
            ) : (
              <DropZonePanel
                onFile={handleFile}
                isLoading={isLoading}
                error={error}
              />
            )}
          </main>

          {/* Right: Detector stack */}
          <aside
            style={{
              background: "var(--bg-panel, #111418)",
              display: "flex",
              flexDirection: "column",
              overflowY: "auto",
            }}
          >
            <div
              style={{
                padding: "7px 12px 6px",
                borderBottom: "1px solid var(--border-subtle, #232830)",
                background: "var(--bg-elevated, #181c21)",
                fontFamily: "var(--font-geist-mono), ui-monospace, monospace",
                fontSize: "10px",
                letterSpacing: "0.16em",
                textTransform: "uppercase",
                color: "var(--fg-faint, #6b7480)",
                flexShrink: 0,
              }}
            >
              Detector Stack
            </div>
            <DetectorGrid states={detectorStates} />
          </aside>
        </div>
      </div>
    </>
  );
}
