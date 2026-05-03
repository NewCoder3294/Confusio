"use client";

import { useRef, useState } from "react";

type TriageVerdict = {
  label: "SUSPECTED_SYNTHETIC" | "INCONCLUSIVE" | "SUSPECTED_AUTHENTIC";
  confidence: "high" | "medium" | "low";
  score: number;
  drivers: string[];
};

type TriageReport = {
  meta: {
    sha256?: string;
    mime_inferred?: string;
    size_bytes?: number;
  };
  provenance: {
    c2pa?: {
      status: string;
      detail?: string;
      summary?: {
        claim_generator_info?: Array<{ name?: string; version?: string | null }>;
      };
    };
  };
  ai_surrogate: {
    model: string;
    backend: string;
    p_ai: number;
    p_real: number;
    note?: string | null;
  };
  exif: {
    fields: Record<string, string | number | boolean>;
    anomalies: string[];
    error?: string;
  };
  verdict: TriageVerdict;
};

type TriageResponse = {
  filename: string;
  uploadedAt: string;
  report: TriageReport;
};

const VERDICT_TONE: Record<TriageVerdict["label"], string> = {
  SUSPECTED_SYNTHETIC: "bg-fail-bg text-fail-fg border-fail-border",
  INCONCLUSIVE: "bg-warn-bg text-warn-fg border-warn-border",
  SUSPECTED_AUTHENTIC: "bg-pass-bg text-pass-fg border-pass-border",
};

const VERDICT_COPY: Record<TriageVerdict["label"], string> = {
  SUSPECTED_SYNTHETIC: "SUSPECTED SYNTHETIC",
  INCONCLUSIVE: "INCONCLUSIVE",
  SUSPECTED_AUTHENTIC: "SUSPECTED AUTHENTIC",
};

export function IntelInbox() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<TriageResponse | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function submit(file: File) {
    setBusy(true);
    setError(null);
    setResult(null);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(URL.createObjectURL(file));

    const fd = new FormData();
    fd.append("image", file);
    try {
      const res = await fetch("/api/intel/triage", { method: "POST", body: fd });
      const body = await res.json();
      if (!res.ok) {
        setError(body.error || `HTTP ${res.status}`);
      } else {
        setResult(body as TriageResponse);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function onPick() {
    inputRef.current?.click();
  }

  return (
    <div className="grid grid-cols-[420px_1fr] gap-6 min-h-[600px]">
      {/* Submit panel */}
      <aside className="flex flex-col gap-4">
        <div className="border border-border-subtle bg-bg-panel">
          <header className="px-4 py-2 border-b border-border-subtle">
            <h2 className="text-[11px] font-mono uppercase tracking-[0.18em] text-fg-faint">
              Submit for triage
            </h2>
          </header>
          <div className="p-4 flex flex-col gap-3">
            <input
              ref={inputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp,image/gif"
              hidden
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) submit(f);
              }}
            />
            <button
              onClick={onPick}
              disabled={busy}
              className="border border-border-default bg-bg-elevated hover:bg-bg-hover px-4 py-3 font-mono text-[12px] uppercase tracking-[0.16em] text-fg-default disabled:opacity-50 disabled:cursor-wait"
            >
              {busy ? "Triaging…" : "Select image file"}
            </button>
            <p className="text-[11px] text-fg-faint italic">
              JPEG, PNG, WebP, or GIF — up to 25 MB. File never leaves the host;
              triage runs locally against C2PA, Titan, SynthID, the
              spectral-surrogate classifier, and EXIF anomaly checks.
            </p>
          </div>
        </div>

        {previewUrl && (
          <div className="border border-border-subtle bg-bg-panel">
            <header className="px-4 py-2 border-b border-border-subtle">
              <h2 className="text-[11px] font-mono uppercase tracking-[0.18em] text-fg-faint">
                Submitted artifact
              </h2>
            </header>
            <div className="aspect-video bg-bg-base flex items-center justify-center overflow-hidden">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={previewUrl}
                alt="Submitted artifact preview"
                className="max-h-full max-w-full object-contain"
              />
            </div>
            {result && (
              <dl className="text-[11px] divide-y divide-border-subtle">
                <KV k="filename" v={result.filename} />
                <KV
                  k="sha-256"
                  v={result.report.meta.sha256 ?? "—"}
                  mono
                />
                <KV
                  k="bytes"
                  v={String(result.report.meta.size_bytes ?? "—")}
                  mono
                />
                <KV
                  k="mime"
                  v={result.report.meta.mime_inferred ?? "—"}
                  mono
                />
                <KV k="received" v={result.uploadedAt} mono />
              </dl>
            )}
          </div>
        )}
      </aside>

      {/* Report panel */}
      <section className="flex flex-col gap-6">
        {error && (
          <div className="border border-fail-border bg-fail-bg px-4 py-3 text-fail-fg text-[12px]">
            <div className="font-mono uppercase tracking-[0.14em] text-[10px] mb-1">
              Triage error
            </div>
            <div className="font-mono text-[12px]">{error}</div>
          </div>
        )}

        {!result && !busy && !error && <EmptyReport />}
        {busy && <BusyReport />}
        {result && <ReportView report={result.report} />}
      </section>
    </div>
  );
}

function EmptyReport() {
  return (
    <div className="border border-border-subtle bg-bg-panel flex-1 flex items-center justify-center">
      <div className="px-8 py-12 text-center max-w-md">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-fg-faint">
          No artifact under triage
        </div>
        <p className="mt-3 text-[13px] text-fg-muted leading-6">
          Submit an image at left. The defensive triage runs four detectors plus
          a metadata anomaly check and produces a verdict with cited drivers.
          Reports are append-only and review the same instruments the offensive
          arm uses to grade its own output.
        </p>
      </div>
    </div>
  );
}

function BusyReport() {
  return (
    <div className="border border-border-subtle bg-bg-panel flex-1 flex items-center justify-center">
      <div className="px-8 py-12 text-center max-w-md">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-fg-faint">
          Triage in progress
        </div>
        <p className="mt-3 text-[13px] text-fg-muted leading-6">
          Reading C2PA manifest, scoring against the spectral surrogate, parsing
          EXIF, computing composite verdict. Local execution — no upload to
          third parties.
        </p>
      </div>
    </div>
  );
}

function ReportView({ report }: { report: TriageReport }) {
  const v = report.verdict;
  return (
    <>
      <div className={`border ${VERDICT_TONE[v.label]} px-5 py-4`}>
        <div className="flex items-baseline justify-between gap-4">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.18em] opacity-80">
              Composite verdict
            </div>
            <div className="font-mono text-2xl mt-1 tracking-wide">
              {VERDICT_COPY[v.label]}
            </div>
          </div>
          <div className="text-right">
            <div className="font-mono text-[10px] uppercase tracking-[0.16em] opacity-80">
              Confidence
            </div>
            <div className="font-mono text-base mt-1 uppercase tracking-wide">
              {v.confidence}
            </div>
            <div className="font-mono text-[10px] mt-[2px] opacity-70">
              score {v.score}
            </div>
          </div>
        </div>
        {v.drivers.length > 0 && (
          <ol className="mt-4 flex flex-col gap-1">
            {v.drivers.map((d, i) => (
              <li key={i} className="text-[12px] leading-5">
                <span className="font-mono opacity-60 mr-2">
                  {String(i + 1).padStart(2, "0")}.
                </span>
                {d}
              </li>
            ))}
          </ol>
        )}
      </div>

      <Section title="Detector breakdown">
        <div className="grid grid-cols-2 gap-2">
          <DetectorTile
            name="C2PA"
            sub="Content Credentials manifest"
            status={c2paStatusText(report.provenance.c2pa)}
            tone={c2paTone(report.provenance.c2pa)}
          />
          <DetectorTile
            name="Spectral surrogate"
            sub={report.ai_surrogate.note ?? report.ai_surrogate.model}
            status={`p(synthetic) = ${report.ai_surrogate.p_ai.toFixed(3)}`}
            tone={
              report.ai_surrogate.p_ai >= 0.7
                ? "fail"
                : report.ai_surrogate.p_ai >= 0.5
                  ? "warn"
                  : "pass"
            }
          />
        </div>
      </Section>

      <Section title="EXIF / metadata">
        {report.exif.error ? (
          <div className="text-fail-fg text-[12px] font-mono">
            {report.exif.error}
          </div>
        ) : (
          <div className="border border-border-subtle bg-bg-panel">
            <dl className="text-[11px] divide-y divide-border-subtle">
              {Object.entries(report.exif.fields).map(([k, val]) => (
                <KV key={k} k={k} v={String(val)} mono />
              ))}
            </dl>
            {report.exif.anomalies.length > 0 && (
              <div className="border-t border-border-subtle bg-warn-bg/40 px-4 py-3">
                <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-warn-fg mb-1">
                  Anomalies
                </div>
                <ul className="flex flex-col gap-1">
                  {report.exif.anomalies.map((a, i) => (
                    <li key={i} className="text-[12px] text-warn-fg">
                      {a}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </Section>

      <details className="border border-border-subtle bg-bg-panel">
        <summary className="px-4 py-2 cursor-pointer text-[11px] font-mono uppercase tracking-[0.14em] text-fg-muted hover:text-fg-default hover:bg-bg-hover">
          Raw triage report (audit-source)
        </summary>
        <pre className="px-4 py-3 text-[11px] overflow-x-auto text-fg-mono whitespace-pre">
          {JSON.stringify(report, null, 2)}
        </pre>
      </details>
    </>
  );
}

function c2paStatusText(c2pa: TriageReport["provenance"]["c2pa"]): string {
  if (!c2pa) return "—";
  if (c2pa.status === "ok") {
    const gens = c2pa.summary?.claim_generator_info ?? [];
    if (gens.length > 0 && gens[0].name) {
      return `Manifest valid — generator: ${gens[0].name}`;
    }
    return "Manifest valid";
  }
  if (c2pa.status === "manifest_not_found") {
    return "No manifest";
  }
  return c2pa.status;
}

function c2paTone(c2pa: TriageReport["provenance"]["c2pa"]): "pass" | "warn" | "fail" {
  if (!c2pa) return "warn";
  if (c2pa.status === "ok") {
    const gens = c2pa.summary?.claim_generator_info ?? [];
    if (gens.length > 0) return "fail"; // generator declared = synthetic
    return "warn";
  }
  return "warn";
}

function DetectorTile({
  name,
  sub,
  status,
  tone,
}: {
  name: string;
  sub: string;
  status: string;
  tone: "pass" | "warn" | "fail";
}) {
  const TONE: Record<typeof tone, string> = {
    pass: "border-pass-border bg-pass-bg text-pass-fg",
    warn: "border-warn-border bg-warn-bg text-warn-fg",
    fail: "border-fail-border bg-fail-bg text-fail-fg",
  };
  return (
    <div className={`border ${TONE[tone]} px-3 py-2`}>
      <div className="flex items-baseline justify-between gap-3">
        <span className="font-mono text-[11px] tracking-[0.16em] text-fg-default">
          {name}
        </span>
        <span className="font-mono text-[10px] uppercase tracking-[0.14em]">
          {tone === "fail" ? "FLAG" : tone === "warn" ? "INSPECT" : "PASS"}
        </span>
      </div>
      <div className="mt-1 text-[11px] font-mono">{status}</div>
      <div className="mt-[2px] text-[10px] opacity-70 italic">{sub}</div>
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <div className="flex items-baseline justify-between mb-2">
        <h2 className="text-[11px] font-mono uppercase tracking-[0.18em] text-fg-faint">
          {title}
        </h2>
      </div>
      {children}
    </section>
  );
}

function KV({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <div className="grid grid-cols-[180px_1fr] gap-3 px-3 py-2">
      <dt className="text-fg-faint uppercase tracking-[0.14em] font-mono text-[10px]">
        {k}
      </dt>
      <dd className={`text-fg-muted ${mono ? "font-mono text-[11px]" : ""} truncate`}>
        {v}
      </dd>
    </div>
  );
}
