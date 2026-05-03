"use client";

import { useRef, useState } from "react";
import { Card, Tabs, Block, Row } from "@/components/surfaces";

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
  SUSPECTED_SYNTHETIC: "border-fail-border bg-fail-bg/40 text-fail-fg",
  INCONCLUSIVE: "border-warn-border bg-warn-bg/40 text-warn-fg",
  SUSPECTED_AUTHENTIC: "border-pass-border bg-pass-bg/40 text-pass-fg",
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

  return (
    <div className="grid grid-cols-[320px_1fr] gap-3 items-start">
      <Card title="Submit">
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
            onClick={() => inputRef.current?.click()}
            disabled={busy}
            className="border border-info-border bg-info-bg/40 hover:bg-info-bg px-4 py-3 font-mono text-[12px] uppercase tracking-[0.16em] text-info-fg disabled:opacity-50 disabled:cursor-wait"
          >
            {busy ? "Triaging…" : "Select image"}
          </button>
          <p className="text-[11px] text-fg-faint italic leading-5">
            JPEG, PNG, WebP, GIF · ≤25 MB. Triage runs locally — no upload
            to third parties.
          </p>
        </div>
        {previewUrl && (
          <Block label="Preview">
            <div className="aspect-video bg-bg-base flex items-center justify-center overflow-hidden border border-border-subtle">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={previewUrl}
                alt="Submitted artifact"
                className="max-h-full max-w-full object-contain"
              />
            </div>
          </Block>
        )}
        {result && (
          <Block label="Submission">
            <dl>
              <Row label="File" value={result.filename} />
              <Row
                label="Mime"
                value={result.report.meta.mime_inferred ?? "—"}
                mono
              />
              <Row
                label="Bytes"
                value={String(result.report.meta.size_bytes ?? "—")}
                mono
              />
              <Row
                label="SHA-256"
                value={(result.report.meta.sha256 ?? "—").slice(0, 32) + "…"}
                mono
              />
              <Row label="Received" value={result.uploadedAt} mono />
            </dl>
          </Block>
        )}
      </Card>

      {/* Right column */}
      {error ? (
        <Card title="Triage error">
          <Block>
            <div className="border border-fail-border bg-fail-bg/40 p-4 text-fail-fg text-[12px] font-mono">
              {error}
            </div>
          </Block>
        </Card>
      ) : busy ? (
        <Card title="Triage in progress">
          <Block>
            <p className="text-[12px] text-fg-muted leading-6">
              Reading C2PA manifest, scoring against the spectral surrogate,
              parsing EXIF, computing composite verdict.
            </p>
          </Block>
        </Card>
      ) : result ? (
        <ReportCard report={result.report} />
      ) : (
        <Card title="No artifact under triage">
          <Block>
            <p className="text-[12px] text-fg-muted leading-6">
              Submit an image at left. Triage runs four detectors plus EXIF
              anomaly checks and produces a composite verdict with cited
              drivers. The same instruments the offensive arm uses to grade
              its own output, inverted.
            </p>
          </Block>
        </Card>
      )}
    </div>
  );
}

function ReportCard({ report }: { report: TriageReport }) {
  const v = report.verdict;
  return (
    <Card title="Triage report">
      <div className={`border-b ${VERDICT_TONE[v.label]} px-5 py-3 flex items-baseline justify-between gap-4`}>
        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.16em] opacity-80">
            Composite verdict
          </div>
          <div className="font-mono text-xl mt-[2px] tracking-wide">
            {VERDICT_COPY[v.label]}
          </div>
        </div>
        <div className="text-right">
          <div className="font-mono text-[10px] uppercase tracking-[0.14em] opacity-80">
            {v.confidence}
          </div>
          <div className="font-mono text-[11px] opacity-70 tabular-nums">
            score {v.score >= 0 ? "+" : ""}
            {v.score}
          </div>
        </div>
      </div>
      <Tabs
        tabs={[
          {
            id: "drivers",
            label: "Drivers",
            count: v.drivers.length,
            panel: <DriversPanel drivers={v.drivers} />,
          },
          {
            id: "detectors",
            label: "Detectors",
            panel: <DetectorsPanel report={report} />,
          },
          {
            id: "exif",
            label: "EXIF",
            count: report.exif.anomalies.length,
            panel: <ExifPanel exif={report.exif} />,
          },
          {
            id: "raw",
            label: "Raw",
            panel: <RawPanel report={report} />,
          },
        ]}
      />
    </Card>
  );
}

function DriversPanel({ drivers }: { drivers: string[] }) {
  if (drivers.length === 0) {
    return (
      <div className="px-4 py-6 text-fg-faint italic text-[12px]">
        No drivers cited.
      </div>
    );
  }
  return (
    <ol>
      {drivers.map((d, i) => (
        <li
          key={i}
          className="grid grid-cols-[40px_1fr] gap-3 px-4 py-2 border-b border-border-subtle last:border-b-0"
        >
          <span className="font-mono text-[11px] text-fg-faint tabular-nums">
            {String(i + 1).padStart(2, "0")}.
          </span>
          <span className="text-[12px] leading-5 text-fg-default">{d}</span>
        </li>
      ))}
    </ol>
  );
}

function DetectorsPanel({ report }: { report: TriageReport }) {
  return (
    <Block>
      <div className="grid grid-cols-2 gap-2">
        <DetectorTile
          name="C2PA"
          sub="Content Credentials"
          status={c2paStatusText(report.provenance.c2pa)}
          tone={c2paTone(report.provenance.c2pa)}
        />
        <DetectorTile
          name="Spectral"
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
    </Block>
  );
}

function ExifPanel({ exif }: { exif: TriageReport["exif"] }) {
  if (exif.error) {
    return (
      <Block>
        <div className="text-fail-fg text-[12px] font-mono">{exif.error}</div>
      </Block>
    );
  }
  return (
    <>
      <Block label="Fields">
        <dl>
          {Object.entries(exif.fields).map(([k, v]) => (
            <Row key={k} label={k} value={String(v)} mono />
          ))}
        </dl>
      </Block>
      {exif.anomalies.length > 0 && (
        <Block label="Anomalies">
          <ul className="flex flex-col gap-1">
            {exif.anomalies.map((a, i) => (
              <li
                key={i}
                className="text-[12px] text-warn-fg leading-5 border-l-2 border-warn-border pl-3"
              >
                {a}
              </li>
            ))}
          </ul>
        </Block>
      )}
    </>
  );
}

function RawPanel({ report }: { report: TriageReport }) {
  return (
    <Block label="Audit-source JSON">
      <pre className="text-[11px] overflow-x-auto text-fg-mono whitespace-pre">
        {JSON.stringify(report, null, 2)}
      </pre>
    </Block>
  );
}

function c2paStatusText(c2pa: TriageReport["provenance"]["c2pa"]): string {
  if (!c2pa) return "—";
  if (c2pa.status === "ok") {
    const gens = c2pa.summary?.claim_generator_info ?? [];
    if (gens.length > 0 && gens[0].name) {
      return `Manifest valid — ${gens[0].name}`;
    }
    return "Manifest valid";
  }
  if (c2pa.status === "manifest_not_found") return "No manifest";
  return c2pa.status;
}

function c2paTone(
  c2pa: TriageReport["provenance"]["c2pa"],
): "pass" | "warn" | "fail" {
  if (!c2pa) return "warn";
  if (c2pa.status === "ok") {
    const gens = c2pa.summary?.claim_generator_info ?? [];
    if (gens.length > 0) return "fail";
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
    pass: "border-pass-border bg-pass-bg/30 text-pass-fg",
    warn: "border-warn-border bg-warn-bg/30 text-warn-fg",
    fail: "border-fail-border bg-fail-bg/30 text-fail-fg",
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
