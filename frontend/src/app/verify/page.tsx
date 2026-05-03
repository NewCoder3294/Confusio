"use client";

import { useCallback, useRef, useState } from "react";
import { PageHeader } from "@/components/surfaces";

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

/* ─────────────────────────────────────────────────────────────────────── */
/* Verdict colors (inline styles — Tailwind v4 JIT may not generate tokens) */
/* ─────────────────────────────────────────────────────────────────────── */

const VERDICT_STYLES: Record<
  Verdict["level"],
  { pill: React.CSSProperties; badge: React.CSSProperties }
> = {
  AUTHENTIC: {
    pill: {
      background: "#16271c",
      border: "1px solid #2d5a3a",
      color: "#9be0a8",
    },
    badge: {
      background: "#16271c",
      border: "1px solid #2d5a3a",
      color: "#9be0a8",
    },
  },
  SUSPECT: {
    pill: {
      background: "#2e2410",
      border: "1px solid #6b4f1c",
      color: "#ffd591",
    },
    badge: {
      background: "#2e2410",
      border: "1px solid #6b4f1c",
      color: "#ffd591",
    },
  },
  SYNTHETIC: {
    pill: {
      background: "#3a1f1f",
      border: "1px solid #6e2b2b",
      color: "#ffb4b4",
    },
    badge: {
      background: "#3a1f1f",
      border: "1px solid #6e2b2b",
      color: "#ffb4b4",
    },
  },
};

const SEVERITY_STYLE: Record<DetectorSignal["severity"], React.CSSProperties> =
  {
    pass: { color: "#6cd690" },
    warn: { color: "#e3b14a" },
    fail: { color: "#e36b6b" },
    "n/a": { color: "#6b7480" },
  };

/* ─────────────────────────────────────────────────────────────────────── */
/* Dossier component                                                         */
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

  const verdictStyle = VERDICT_STYLES[verdict.level];

  const provenance = signals.filter((s) =>
    ["c2pa", "synthid", "titan"].includes(s.detector),
  );
  const synthesis = signals.filter((s) =>
    ["ai_classifier", "exif"].includes(s.detector),
  );
  const tamper = signals.filter((s) =>
    ["ela", "phash"].includes(s.detector),
  );

  function provenanceConclusion(sigs: DetectorSignal[]): string {
    const fails = sigs.filter((s) => s.severity === "fail");
    const passes = sigs.filter((s) => s.severity === "pass");
    if (fails.length > 0) {
      return `Provenance chain compromised: ${fails.map((s) => s.detector).join(", ")} indicate manipulation.`;
    }
    if (passes.length > 0) {
      return `Provenance chain intact across checked detectors.`;
    }
    return "No provenance signals detected — absence is expected for unembedded imagery.";
  }

  function synthesisConclusion(sigs: DetectorSignal[]): string {
    const fails = sigs.filter((s) => s.severity === "fail");
    if (fails.length > 0) {
      return `Synthesis indicators positive: ${fails.map((s) => s.evidence).join("; ")}.`;
    }
    return "No synthesis indicators detected.";
  }

  function tamperConclusion(sigs: DetectorSignal[]): string {
    const fails = sigs.filter((s) => s.severity === "fail");
    if (fails.length > 0) {
      return `Tamper evidence detected: ${fails.map((s) => s.evidence).join("; ")}.`;
    }
    return "No tamper evidence detected. ELA and perceptual hash within nominal bounds.";
  }

  const isoTs = new Date(submitted_at).toISOString();

  return (
    <div
      style={{
        fontFamily: "var(--font-geist-mono), ui-monospace, monospace",
        fontSize: "12px",
        color: "var(--fg-default, #e6e9ec)",
        display: "flex",
        flexDirection: "column",
        gap: "0",
      }}
    >
      {/* Verify Another button */}
      <div
        style={{
          padding: "10px 16px",
          borderBottom: "1px solid var(--border-subtle, #232830)",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <button
          onClick={onVerifyAnother}
          style={{
            fontFamily: "inherit",
            fontSize: "11px",
            letterSpacing: "0.14em",
            textTransform: "uppercase",
            background: "transparent",
            border: "1px solid var(--border-default, #2c333c)",
            color: "var(--fg-muted, #9aa3ad)",
            padding: "4px 12px",
            cursor: "pointer",
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLButtonElement).style.color =
              "var(--fg-default, #e6e9ec)";
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLButtonElement).style.color =
              "var(--fg-muted, #9aa3ad)";
          }}
        >
          Verify Another
        </button>
      </div>

      {/* Dossier header */}
      <div
        style={{
          padding: "10px 16px",
          borderBottom: "1px solid var(--border-subtle, #232830)",
          background: "var(--bg-elevated, #181c21)",
          fontSize: "10px",
          letterSpacing: "0.14em",
          textTransform: "uppercase",
          color: "var(--fg-faint, #6b7480)",
        }}
      >
        VERIFY · DOSSIER {isoTs} · OPERATOR {operator}
      </div>

      {/* Subject row */}
      <div
        style={{
          padding: "12px 16px",
          borderBottom: "1px solid var(--border-subtle, #232830)",
          display: "flex",
          gap: "16px",
          alignItems: "flex-start",
        }}
      >
        {/* Thumbnail */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={dataUrl}
          alt="Subject image"
          style={{
            width: "90px",
            height: "60px",
            objectFit: "cover",
            border: "1px solid var(--border-default, #2c333c)",
            flexShrink: 0,
          }}
        />
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "96px 1fr",
            gap: "4px 8px",
            fontSize: "11px",
          }}
        >
          <span style={{ color: "var(--fg-faint, #6b7480)", textTransform: "uppercase", letterSpacing: "0.12em", fontSize: "10px" }}>FILE</span>
          <span style={{ color: "var(--fg-mono, #c4cad1)" }}>{fileName}</span>
          <span style={{ color: "var(--fg-faint, #6b7480)", textTransform: "uppercase", letterSpacing: "0.12em", fontSize: "10px" }}>SHA256</span>
          <span style={{ color: "var(--fg-mono, #c4cad1)" }}>{sha256.slice(0, 32)}…</span>
          <span style={{ color: "var(--fg-faint, #6b7480)", textTransform: "uppercase", letterSpacing: "0.12em", fontSize: "10px" }}>MIME</span>
          <span style={{ color: "var(--fg-mono, #c4cad1)" }}>{mimeType}</span>
          <span style={{ color: "var(--fg-faint, #6b7480)", textTransform: "uppercase", letterSpacing: "0.12em", fontSize: "10px" }}>BYTES</span>
          <span style={{ color: "var(--fg-mono, #c4cad1)" }}>
            {fileSize.toLocaleString()}
          </span>
        </div>
      </div>

      {/* §1 Provenance */}
      <DossierSection
        heading="§1 Provenance"
        signals={provenance}
        conclusion={provenanceConclusion(provenance)}
      />

      {/* §2 Synthesis Indicators */}
      <DossierSection
        heading="§2 Synthesis Indicators"
        signals={synthesis}
        conclusion={synthesisConclusion(synthesis)}
      />

      {/* §3 Tamper Evidence */}
      <DossierSection
        heading="§3 Tamper Evidence"
        signals={tamper}
        conclusion={tamperConclusion(tamper)}
      />

      {/* Footer verdict */}
      <div
        style={{
          padding: "12px 16px",
          borderTop: "1px solid var(--border-default, #2c333c)",
          background: "var(--bg-elevated, #181c21)",
          display: "flex",
          alignItems: "center",
          gap: "16px",
          flexWrap: "wrap",
        }}
      >
        <span
          style={{
            ...verdictStyle.badge,
            padding: "4px 12px",
            fontFamily: "var(--font-geist-mono), ui-monospace, monospace",
            fontSize: "11px",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
          }}
        >
          {verdict.level}
        </span>
        <span style={{ color: "var(--fg-faint, #6b7480)", fontSize: "11px" }}>
          confidence{" "}
          <span style={{ color: "var(--fg-mono, #c4cad1)" }}>
            {verdict.confidence.toFixed(2)}
          </span>
        </span>
        <span
          style={{
            color: "var(--fg-muted, #9aa3ad)",
            fontSize: "12px",
            fontFamily: "var(--font-geist-sans), system-ui, sans-serif",
            flex: "1",
          }}
        >
          {verdict.summary}
        </span>
      </div>
    </div>
  );
}

function DossierSection({
  heading,
  signals,
  conclusion,
}: {
  heading: string;
  signals: DetectorSignal[];
  conclusion: string;
}) {
  return (
    <div
      style={{
        borderBottom: "1px solid var(--border-subtle, #232830)",
        padding: "12px 16px",
      }}
    >
      <div
        style={{
          fontSize: "10px",
          letterSpacing: "0.16em",
          textTransform: "uppercase",
          color: "var(--fg-faint, #6b7480)",
          marginBottom: "8px",
        }}
      >
        {heading}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "4px", marginBottom: "10px" }}>
        {signals.map((s) => (
          <div key={s.detector} style={{ display: "flex", gap: "12px", alignItems: "baseline" }}>
            <span
              style={{
                fontFamily: "var(--font-geist-mono), ui-monospace, monospace",
                fontSize: "11px",
                color: "var(--fg-muted, #9aa3ad)",
                minWidth: "100px",
                textTransform: "uppercase",
                letterSpacing: "0.1em",
              }}
            >
              {s.detector}
            </span>
            <span style={{ ...SEVERITY_STYLE[s.severity], fontSize: "10px", letterSpacing: "0.12em", textTransform: "uppercase", minWidth: "40px" }}>
              {s.severity}
            </span>
            <span style={{ color: "var(--fg-muted, #9aa3ad)", fontSize: "11px" }}>
              {s.severity === "n/a" ? "detector unavailable" : s.evidence}
            </span>
          </div>
        ))}
      </div>
      <p
        style={{
          fontFamily: "var(--font-geist-sans), system-ui, sans-serif",
          fontSize: "12px",
          color: "var(--fg-muted, #9aa3ad)",
          lineHeight: "1.6",
          margin: 0,
        }}
      >
        {conclusion}
      </p>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────── */
/* Sidebar entry pill                                                        */
/* ─────────────────────────────────────────────────────────────────────── */

function SidebarRow({
  entry,
  isActive,
  onClick,
}: {
  entry: SessionEntry;
  isActive: boolean;
  onClick: () => void;
}) {
  const verdictStyle = VERDICT_STYLES[entry.verdictLevel];
  return (
    <button
      onClick={onClick}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "8px",
        padding: "8px 12px",
        borderBottom: "1px solid var(--border-subtle, #232830)",
        background: isActive
          ? "var(--bg-elevated, #181c21)"
          : "transparent",
        borderLeft: isActive
          ? "2px solid var(--info-fg, #5fb8d6)"
          : "2px solid transparent",
        cursor: "pointer",
        width: "100%",
        textAlign: "left",
        fontFamily: "var(--font-geist-mono), ui-monospace, monospace",
      }}
    >
      <span
        style={{
          fontSize: "10px",
          color: "var(--fg-mono, #c4cad1)",
          flex: 1,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
      >
        {entry.sha256Prefix}
      </span>
      <span
        style={{
          ...verdictStyle.pill,
          fontSize: "9px",
          letterSpacing: "0.12em",
          textTransform: "uppercase",
          padding: "2px 6px",
          flexShrink: 0,
        }}
      >
        {entry.verdictLevel}
      </span>
    </button>
  );
}

/* ─────────────────────────────────────────────────────────────────────── */
/* Drop zone                                                                 */
/* ─────────────────────────────────────────────────────────────────────── */

function DropZone({
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

  const handleDragLeave = useCallback(() => {
    setIsDragging(false);
  }, []);

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

  return (
    <div style={{ padding: "24px 16px", display: "flex", flexDirection: "column", gap: "12px" }}>
      {/* Error banner */}
      {error && (
        <div
          style={{
            background: "var(--fail-bg, #2a1212)",
            border: "1px solid var(--fail-border, #4a1f1f)",
            color: "var(--fail-fg, #e36b6b)",
            padding: "10px 14px",
            fontFamily: "var(--font-geist-mono), ui-monospace, monospace",
            fontSize: "11px",
            letterSpacing: "0.1em",
          }}
        >
          <span style={{ textTransform: "uppercase", letterSpacing: "0.14em" }}>
            {error.code}
          </span>{" "}
          — {error.message}
        </div>
      )}

      {/* Drop zone box */}
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
          border: `1px dashed ${isDragging ? "var(--info-fg, #5fb8d6)" : "var(--border-default, #2c333c)"}`,
          background: isDragging
            ? "var(--info-bg, #0e2530)"
            : "var(--bg-panel, #111418)",
          padding: "48px 24px",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: "10px",
          cursor: isLoading ? "wait" : "pointer",
          transition: "border-color 0.15s, background 0.15s",
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
              (this may take a few seconds)
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
              Drop image here or click to choose file
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
/* Page                                                                      */
/* ─────────────────────────────────────────────────────────────────────── */

export default function VerifyPage() {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<{ code: string; message: string } | null>(
    null,
  );
  const [session, setSession] = useState<SessionEntry[]>([]);
  const [activeIdx, setActiveIdx] = useState<number | null>(null);

  const activeEntry = activeIdx !== null ? session[activeIdx] : null;

  const handleFile = useCallback(async (file: File) => {
    setIsLoading(true);
    setError(null);

    // Read as data URL for thumbnail display (done before the fetch so the UI
    // can render the thumbnail even if we need to show the dossier right away)
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
      const res = await fetch("/api/verify", {
        method: "POST",
        body: form,
      });

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
        setIsLoading(false);
        return;
      }

      data = (await res.json()) as VerifyResponse;
    } catch (err) {
      setError({
        code: "network_error",
        error: err instanceof Error ? err.message : String(err),
      } as unknown as { code: string; message: string });
      setIsLoading(false);
      return;
    }

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

    setSession((prev) => {
      const next = [entry, ...prev];
      setActiveIdx(0);
      return next;
    });
    setIsLoading(false);
  }, []);

  const handleVerifyAnother = useCallback(() => {
    setActiveIdx(null);
    setError(null);
  }, []);

  return (
    <>
      <PageHeader
        eyebrow="Defensive arm · Counter-deception"
        title="VERIFY"
        brief="Drop an inbound image to run the full seven-detector provenance and synthesis stack. Every verification is recorded in the audit log."
      />

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "220px 1fr",
          flex: "1",
          minHeight: "0",
          overflow: "hidden",
        }}
      >
        {/* Sidebar */}
        <aside
          style={{
            borderRight: "1px solid var(--border-subtle, #232830)",
            background: "var(--bg-panel, #111418)",
            display: "flex",
            flexDirection: "column",
            overflowY: "auto",
          }}
        >
          <div
            style={{
              padding: "8px 12px 6px",
              borderBottom: "1px solid var(--border-subtle, #232830)",
              background: "var(--bg-elevated, #181c21)",
              fontFamily: "var(--font-geist-mono), ui-monospace, monospace",
              fontSize: "10px",
              letterSpacing: "0.16em",
              textTransform: "uppercase",
              color: "var(--fg-faint, #6b7480)",
            }}
          >
            Session
          </div>
          {session.length === 0 ? (
            <div
              style={{
                padding: "20px 12px",
                fontFamily: "var(--font-geist-sans), system-ui, sans-serif",
                fontSize: "12px",
                color: "var(--fg-faint, #6b7480)",
                fontStyle: "italic",
              }}
            >
              No verifications yet.
            </div>
          ) : (
            session.map((entry, idx) => (
              <SidebarRow
                key={entry.artifactId}
                entry={entry}
                isActive={idx === activeIdx}
                onClick={() => setActiveIdx(idx)}
              />
            ))
          )}
        </aside>

        {/* Main content area */}
        <main
          style={{
            flex: "1",
            minHeight: "0",
            overflowY: "auto",
            background: "var(--bg-base, #0a0c0e)",
          }}
        >
          {activeEntry ? (
            <div
              style={{
                border: "1px solid var(--border-default, #2c333c)",
                margin: "16px",
                background: "var(--bg-panel, #111418)",
              }}
            >
              <Dossier
                entry={activeEntry}
                onVerifyAnother={handleVerifyAnother}
              />
            </div>
          ) : (
            <div>
              <DropZone
                onFile={handleFile}
                isLoading={isLoading}
                error={error}
              />
              {/* Bottom note */}
              <div
                style={{
                  padding: "0 24px 24px",
                  fontFamily: "var(--font-geist-sans), system-ui, sans-serif",
                  fontSize: "11px",
                  color: "var(--fg-faint, #6b7480)",
                  lineHeight: "1.6",
                }}
              >
                Detector stack: C2PA · SynthID · Titan · AI-gen · EXIF · ELA ·
                pHash. Each verification is recorded in the audit log.
              </div>
            </div>
          )}
        </main>
      </div>
    </>
  );
}
