"use client";

import { useEffect, useState } from "react";
import { Block, Row } from "@/components/surfaces";

type Meta = {
  missionId: string;
  channel: string;
  prompt: string;
  exif: {
    donor: string;
    claims: Record<string, string>;
    outputPath: string;
  };
  steg: {
    payload: string;
    keyHex: string;
    outputPath: string;
    capacityBits: number;
    usedBits: number;
    fractionUsed: number;
    framing: string;
  };
};

/**
 * Reads the per-mission metadata sidecar produced by mendacity.process_artifact
 * and renders the actual injected EXIF + steg payload + recovery key. No
 * templated copy — this is what was really baked into the artifact.
 */
export function InjectionPanel({ missionId }: { missionId: string }) {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pollAttempts, setPollAttempts] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let attempts = 0;
    async function fetchMeta() {
      if (cancelled) return;
      attempts++;
      try {
        const res = await fetch(
          `/api/campaign-image/${encodeURIComponent(missionId)}/meta`,
          { cache: "no-store" },
        );
        if (cancelled) return;
        if (res.ok) {
          setMeta(await res.json());
          setError(null);
          return;
        }
        if (res.status === 404) {
          setPollAttempts(attempts);
          if (attempts < 30) setTimeout(fetchMeta, 4000);
          else setError("Metadata not produced — image generation may have failed.");
          return;
        }
        setError(`HTTP ${res.status}`);
      } catch (e) {
        if (cancelled) return;
        setPollAttempts(attempts);
        if (attempts < 30) setTimeout(fetchMeta, 4000);
        else setError((e as Error).message);
      }
    }
    setMeta(null);
    setError(null);
    setPollAttempts(0);
    fetchMeta();
    return () => {
      cancelled = true;
    };
  }, [missionId]);

  if (error) {
    return (
      <Block>
        <p className="text-fail-fg text-[12px] font-mono">{error}</p>
      </Block>
    );
  }

  if (!meta) {
    return (
      <Block>
        <div className="flex flex-col items-center gap-2 px-6 py-8">
          <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-info-fg animate-pulse">
            Awaiting metadata · post-processing in flight
          </div>
          <div className="font-mono text-[9px] text-fg-faint">
            Polling every 4s · attempt {pollAttempts}
          </div>
        </div>
      </Block>
    );
  }

  return (
    <>
      <Block label="Surface 1 — EXIF transplant (camera realism)">
        <p className="text-[12px] text-fg-muted leading-5 mb-2">
          Donor JPEG{" "}
          <span className="font-mono text-fg-default">{meta.exif.donor}</span>{" "}
          re-encoded onto the DALL-E PNG via{" "}
          <span className="font-mono text-fg-default">
            scripts/apply_jpeg_exif.py transplant
          </span>
          . Defeats EXIF-only camera-attribution heuristics; the file appears
          captured by the donor device. Pixel dimensions harmonized; GPS
          omitted by default.
        </p>
        <dl className="border-t border-border-subtle pt-2">
          {Object.entries(meta.exif.claims).map(([k, v]) => (
            <Row key={k} label={k} value={v} mono />
          ))}
        </dl>
        <div className="mt-3 text-[10px] font-mono text-fg-faint">
          file → {meta.exif.outputPath.split("/").slice(-2).join("/")}
        </div>
      </Block>

      <Block label="Surface 2 — Steganographic payload (LSB, key-permuted)">
        <p className="text-[12px] text-fg-muted leading-5 mb-2">
          Embedded into a sibling PNG via{" "}
          <span className="font-mono text-fg-default">forensic.steg.embed</span>
          . Adaptive-LSB with HMAC-SHA256-derived bit placement; framed as{" "}
          <span className="font-mono text-fg-default">{meta.steg.framing}</span>
          . Recoverable only with the operator&apos;s key; statistical detection
          requires &gt;5% LSB density (we use{" "}
          {(meta.steg.fractionUsed * 100).toFixed(2)}%).
        </p>
        <pre className="border border-border-subtle bg-bg-base px-3 py-2 text-[11px] font-mono text-fg-mono whitespace-pre-wrap leading-5 mb-3">
          {meta.steg.payload}
        </pre>
        <dl className="border-t border-border-subtle pt-2">
          <Row
            label="Key (hex)"
            value={`${meta.steg.keyHex.slice(0, 32)}…`}
            mono
          />
          <Row label="Capacity" value={`${meta.steg.capacityBits.toLocaleString()} bits`} mono />
          <Row
            label="Used"
            value={`${meta.steg.usedBits.toLocaleString()} bits (${(meta.steg.fractionUsed * 100).toFixed(2)}%)`}
            mono
          />
        </dl>
        <div className="mt-3 text-[10px] font-mono text-fg-faint">
          file → {meta.steg.outputPath.split("/").slice(-2).join("/")} · view
          via{" "}
          <a
            className="text-info-fg underline"
            href={`/api/campaign-image/${encodeURIComponent(missionId)}?variant=steg`}
            target="_blank"
            rel="noopener noreferrer"
          >
            ?variant=steg
          </a>
        </div>
      </Block>

      <Block label="Bias targets">
        <ul className="text-[12px] text-fg-muted leading-6 list-none">
          {[
            "OpenAI Moderation API (image)",
            "Anthropic Claude Vision (OCR + summarization)",
            "Google Gemini Vision",
            "Hive Image Moderation (vision prompt path)",
            "Generic OSINT pipelines that LLM-caption inbound media",
          ].map((line) => (
            <li key={line} className="flex items-baseline gap-2">
              <span className="font-mono text-fg-faint">·</span>
              {line}
            </li>
          ))}
        </ul>
      </Block>

      <Block label="Operator note">
        <p className="text-[11px] text-fg-faint italic leading-5">
          Two surfaces stack: the JPEG carries iPhone EXIF for downstream
          camera-attribution heuristics; the sibling PNG carries the steg
          payload for downstream LLM summarizers that OCR images. Defenders
          harden against this class quickly — treat as a one-shot multiplier,
          not a standing capability.
        </p>
      </Block>
    </>
  );
}
