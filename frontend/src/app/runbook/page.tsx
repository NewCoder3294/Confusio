import Link from "next/link";

export const metadata = {
  title: "Mendacity — Runbook",
};

export default function RunbookPage() {
  return (
    <div className="flex-1 flex flex-col">
      <section className="border-b border-border-subtle bg-bg-panel">
        <div className="max-w-[1400px] mx-auto px-6 py-5">
          <div className="font-mono text-[10px] tracking-[0.18em] text-classified uppercase">
            Operator Reference — Standard Operating Procedure
          </div>
          <h1 className="mt-1 text-2xl text-fg-default tracking-wide font-medium">
            Runbook
          </h1>
          <p className="mt-2 text-[13px] text-fg-muted leading-6 max-w-[820px]">
            Bound reference for operators: authority lanes, approval chain,
            detector glossary, verdict semantics, escalation paths. Treat as
            the canonical source — the live system surfaces conform to this
            document, not the other way around.
          </p>
        </div>
      </section>

      <div className="max-w-[980px] w-full mx-auto px-6 py-8 flex flex-col gap-10">
        <Toc
          items={[
            ["authority", "Authority & lane"],
            ["approval", "Approval chain"],
            ["detectors", "Detector glossary"],
            ["verdicts", "Verdict semantics"],
            ["personas", "Persona discipline"],
            ["incidents", "Incident response"],
          ]}
        />

        <Section id="authority" title="Authority & lane" anchor="A">
          <p>
            All operations execute under <strong>Title 10 §1631</strong>{" "}
            military information operations authority. Targeting is restricted
            to non-U.S. persons via sandbox-only channels. Live delivery to
            production endpoints is not enabled in this build; the engine
            refuses any mission whose target channel is not on the{" "}
            <Link href="/channels" className="text-info-fg underline">
              sandbox allowlist
            </Link>
            .
          </p>
          <Note tone="warn">
            <strong>Title 50</strong> activity (covert action) is a different
            authority and is out of scope. Any intent that reads as Title 50
            (clandestine influence not attributable to the U.S. government,
            domestic targeting, third-country political effects) must be
            refused at the operator console and escalated.
          </Note>
        </Section>

        <Section id="approval" title="Approval chain" anchor="B">
          <p>
            Every dispatched mission is recorded with the full operator
            decision history in the audit trail. The standing chain:
          </p>
          <ol className="border border-border-subtle bg-bg-panel divide-y divide-border-subtle font-mono text-[12px]">
            <li className="grid grid-cols-[40px_140px_1fr] gap-3 px-4 py-2">
              <span className="text-fg-faint tabular-nums">01.</span>
              <span className="text-fg-default tracking-wide">J2</span>
              <span className="text-fg-muted">
                Director of Intelligence — sets operational intent
              </span>
            </li>
            <li className="grid grid-cols-[40px_140px_1fr] gap-3 px-4 py-2">
              <span className="text-fg-faint tabular-nums">02.</span>
              <span className="text-fg-default tracking-wide">OGC</span>
              <span className="text-fg-muted">
                Office of General Counsel — reviews authority + targeting
              </span>
            </li>
            <li className="grid grid-cols-[40px_140px_1fr] gap-3 px-4 py-2">
              <span className="text-fg-faint tabular-nums">03.</span>
              <span className="text-fg-default tracking-wide">Operator</span>
              <span className="text-fg-muted">
                Per-post approval at the console — every artifact, every
                corroborator
              </span>
            </li>
          </ol>
          <p>
            Operator approval is per-post, not per-campaign. Backstop posts
            from corroborating personas each require their own approval before
            transmission.
          </p>
        </Section>

        <Section id="detectors" title="Detector glossary" anchor="C">
          <p>
            The same four signals run on both arms (offensive self-grading and
            defensive triage). What each one actually measures:
          </p>
          <Detector
            name="C2PA"
            sub="Coalition for Content Provenance and Authenticity"
            what="Reads the C2PA JUMBF manifest embedded by the originating tool. When present and signed by a known generator (OpenAI, Adobe, Stability), the artifact is by definition synthetic."
            limit="A missing manifest is not evidence of authenticity — most cameras don't emit one. Read 'manifest_not_found' as neutral."
          />
          <Detector
            name="Amazon Titan watermark"
            sub="Invisible watermark applied by Bedrock image generators"
            what="Bit-pattern detection in DCT coefficients. Reports MACHINE_GENERATED_DETECTED with a confidence bucket."
            limit="Only present in images generated by Bedrock. Negative result tells you nothing about non-Bedrock generators."
          />
          <Detector
            name="Google SynthID"
            sub="Invisible watermark for Imagen / VertexAI"
            what="Spectral watermark detection. Reports WATERMARKED / NOT_WATERMARKED."
            limit="SynthID survives mild crops + recompression but is removable with focused stripping. Negative result on a tampered image is suggestive, not proof."
          />
          <Detector
            name="Spectral surrogate"
            sub="Radial-spectrum 1/f^α distance"
            what="Public surrogate of pixel-level CNN classifiers (sdxl-detector class). Returns p(synthetic) ∈ [0,1]."
            limit="Defeated by laundering (re-photograph + chroma rebalance + noise blend). Use as one signal among several, not a verdict on its own."
          />
        </Section>

        <Section id="verdicts" title="Verdict semantics — Intel Inbox" anchor="D">
          <p>
            The <Link href="/intel" className="text-info-fg underline">
              defensive triage
            </Link>{" "}
            composite score:
          </p>
          <ul className="border border-border-subtle bg-bg-panel divide-y divide-border-subtle text-[12px]">
            <li className="px-4 py-3 grid grid-cols-[200px_60px_1fr] gap-4 items-baseline">
              <span className="font-mono uppercase tracking-[0.16em] text-fail-fg">
                Suspected synthetic
              </span>
              <span className="font-mono text-fg-faint tabular-nums">
                ≥ +4
              </span>
              <span className="text-fg-muted">
                C2PA manifest declares a generator, OR multiple anomalies
                stack. Treat as adversary deception until proven otherwise.
              </span>
            </li>
            <li className="px-4 py-3 grid grid-cols-[200px_60px_1fr] gap-4 items-baseline">
              <span className="font-mono uppercase tracking-[0.16em] text-warn-fg">
                Inconclusive
              </span>
              <span className="font-mono text-fg-faint tabular-nums">
                −1 .. +3
              </span>
              <span className="text-fg-muted">
                Mixed signal. Escalate to manual analyst review before
                actioning.
              </span>
            </li>
            <li className="px-4 py-3 grid grid-cols-[200px_60px_1fr] gap-4 items-baseline">
              <span className="font-mono uppercase tracking-[0.16em] text-pass-fg">
                Suspected authentic
              </span>
              <span className="font-mono text-fg-faint tabular-nums">
                ≤ −2
              </span>
              <span className="text-fg-muted">
                No detector signal, EXIF coherent with claimed device,
                spectral score well below the laundering band. Still not a
                positive proof of authenticity — only an absence of evidence
                of synthesis.
              </span>
            </li>
          </ul>
        </Section>

        <Section id="personas" title="Persona discipline" anchor="E">
          <p>
            Personas are stable identities with declared geographic anchors,
            posting cadence, vocabulary, and a corroboration graph. Discipline
            rules:
          </p>
          <ul className="list-disc pl-6 flex flex-col gap-1 text-[13px]">
            <li>
              <strong>One persona, one voice.</strong> Style drift across
              posts is the single most common attribution slip. The voice
              profile in <Link href="/personas" className="text-info-fg underline">/personas</Link>{" "}
              is the canonical reference.
            </li>
            <li>
              <strong>Cadence respect.</strong> Posting outside a
              persona&apos;s declared active hours is a tell. Use the cadence
              pill on each persona detail view.
            </li>
            <li>
              <strong>Corroboration via graph only.</strong> Backstop
              corroborators must be on the seed&apos;s{" "}
              <span className="font-mono">knows</span> edges. Random adjacent
              personas reading as a coordinated cell is the fast path to
              attribution.
            </li>
            <li>
              <strong>No persona used twice in a 24h window across
              campaigns.</strong> Cross-campaign reuse breaks the persona&apos;s
              cover.
            </li>
          </ul>
        </Section>

        <Section id="incidents" title="Incident response" anchor="F">
          <p>
            If a mission appears to have leaked attribution, been flagged
            externally, or produced unintended downstream effects:
          </p>
          <ol className="list-decimal pl-6 flex flex-col gap-1 text-[13px]">
            <li>
              Hit <span className="font-mono">abort-mission</span> in Foundry
              immediately — this writes an abort flag the engine respects on
              its next tick.
            </li>
            <li>
              Disable the affected persona&apos;s session in{" "}
              <span className="font-mono">social/sessions/</span>. Do NOT
              delete; preserve for forensic chain-of-custody.
            </li>
            <li>
              Snapshot the audit trail (
              <Link href="/audit" className="text-info-fg underline">
                /audit
              </Link>
              ) and append an incident record with the mission_id, time of
              detection, and observed external signal.
            </li>
            <li>
              Notify J2 and OGC within 1 operating hour. Do not modify
              channel allowlists or persona profiles until incident review
              concludes.
            </li>
          </ol>
        </Section>
      </div>
    </div>
  );
}

function Toc({ items }: { items: Array<[string, string]> }) {
  return (
    <nav className="border border-border-subtle bg-bg-panel">
      <header className="px-4 py-2 border-b border-border-subtle">
        <h2 className="font-mono text-[11px] uppercase tracking-[0.18em] text-fg-faint">
          Contents
        </h2>
      </header>
      <ol className="px-4 py-3 grid grid-cols-2 gap-x-6 gap-y-1 text-[12px]">
        {items.map(([id, label], i) => (
          <li key={id} className="flex items-baseline gap-3">
            <span className="font-mono text-fg-faint w-6 tabular-nums text-[10px]">
              {String.fromCharCode(65 + i)}.
            </span>
            <a
              href={`#${id}`}
              className="text-fg-default hover:text-info-fg transition-colors"
            >
              {label}
            </a>
          </li>
        ))}
      </ol>
    </nav>
  );
}

function Section({
  id,
  title,
  anchor,
  children,
}: {
  id: string;
  title: string;
  anchor: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="flex flex-col gap-3 scroll-mt-12">
      <header className="border-b border-border-subtle pb-2">
        <div className="flex items-baseline gap-3">
          <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-fg-faint">
            §{anchor}
          </span>
          <h2 className="text-lg text-fg-default tracking-wide font-medium">
            {title}
          </h2>
        </div>
      </header>
      <div className="flex flex-col gap-3 text-[13px] text-fg-muted leading-7">
        {children}
      </div>
    </section>
  );
}

function Note({
  tone,
  children,
}: {
  tone: "warn" | "info";
  children: React.ReactNode;
}) {
  const TONE = {
    warn: "border-warn-border bg-warn-bg/40 text-warn-fg",
    info: "border-info-border bg-info-bg/40 text-info-fg",
  };
  return (
    <div className={`border ${TONE[tone]} px-4 py-3 text-[12px] leading-6`}>
      {children}
    </div>
  );
}

function Detector({
  name,
  sub,
  what,
  limit,
}: {
  name: string;
  sub: string;
  what: string;
  limit: string;
}) {
  return (
    <article className="border border-border-subtle bg-bg-panel">
      <header className="px-4 py-2 border-b border-border-subtle">
        <div className="flex items-baseline justify-between gap-3">
          <span className="font-mono text-[12px] tracking-[0.16em] text-fg-default">
            {name}
          </span>
          <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-fg-faint italic">
            {sub}
          </span>
        </div>
      </header>
      <dl className="text-[12px] divide-y divide-border-subtle">
        <div className="grid grid-cols-[120px_1fr] gap-4 px-4 py-2">
          <dt className="font-mono text-[10px] uppercase tracking-[0.14em] text-fg-faint">
            What it measures
          </dt>
          <dd className="text-fg-default leading-6">{what}</dd>
        </div>
        <div className="grid grid-cols-[120px_1fr] gap-4 px-4 py-2">
          <dt className="font-mono text-[10px] uppercase tracking-[0.14em] text-fg-faint">
            Limitation
          </dt>
          <dd className="text-fg-muted leading-6 italic">{limit}</dd>
        </div>
      </dl>
    </article>
  );
}
