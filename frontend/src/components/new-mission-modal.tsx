"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

type Channel = {
  id: string;
  displayName: string;
  audienceProfile: string;
};

type PersonaLite = {
  id: string;
  name: string;
  language: string;
  geoAnchor: string;
  bioShort: string;
  knows: string[];
};

type DispatchResult = {
  ok: true;
  missionId: string;
  campaignId: string;
  campaignError: string | null;
};

type Step = "target" | "persona" | "artifact" | "review";

const STEPS: Step[] = ["target", "persona", "artifact", "review"];
const STEP_LABEL: Record<Step, string> = {
  target: "Target",
  persona: "Cast",
  artifact: "Artifact",
  review: "Review",
};

export function NewMissionModal({
  channels,
  personas,
  open,
  onClose,
}: {
  channels: Channel[];
  personas: PersonaLite[];
  open: boolean;
  onClose: () => void;
}) {
  const router = useRouter();
  const [step, setStep] = useState<Step>("target");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DispatchResult | null>(null);

  const [form, setForm] = useState({
    operator: "J2-INSCOM-Demo",
    targetChannel: channels[0]?.id ?? "",
    audienceProfile: channels[0]?.audienceProfile ?? "",
    seedPersonaId: personas[0]?.id ?? "",
    corroboratorPersonaIds: [] as string[],
    artifactPrompt: "",
  });

  const personasById = useMemo(
    () => new Map(personas.map((p) => [p.id, p])),
    [personas],
  );
  const seed = personasById.get(form.seedPersonaId);

  // Suggested corroborators = the seed's known graph, minus seed.
  const suggested = useMemo(() => {
    if (!seed) return [];
    return seed.knows
      .map((id) => personasById.get(id))
      .filter((p): p is PersonaLite => Boolean(p));
  }, [seed, personasById]);

  // When seed changes, default corroborators to all suggested.
  useEffect(() => {
    setForm((f) => ({
      ...f,
      corroboratorPersonaIds: suggested.map((p) => p.id),
    }));
  }, [suggested]);

  // Reset when reopened
  useEffect(() => {
    if (open) {
      setStep("target");
      setError(null);
      setResult(null);
    }
  }, [open]);

  // Esc closes
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  function selectChannel(id: string) {
    const c = channels.find((c) => c.id === id);
    setForm((f) => ({
      ...f,
      targetChannel: id,
      audienceProfile: c?.audienceProfile ?? f.audienceProfile,
    }));
  }

  function toggleCorroborator(id: string) {
    setForm((f) => ({
      ...f,
      corroboratorPersonaIds: f.corroboratorPersonaIds.includes(id)
        ? f.corroboratorPersonaIds.filter((x) => x !== id)
        : [...f.corroboratorPersonaIds, id],
    }));
  }

  const canAdvance: Record<Step, boolean> = {
    target: Boolean(form.targetChannel && form.audienceProfile.trim()),
    persona: Boolean(form.seedPersonaId),
    artifact: form.artifactPrompt.trim().length > 0,
    review: true,
  };

  const stepIdx = STEPS.indexOf(step);
  const next = () => {
    if (!canAdvance[step]) return;
    if (stepIdx < STEPS.length - 1) setStep(STEPS[stepIdx + 1]);
  };
  const back = () => {
    if (stepIdx > 0) setStep(STEPS[stepIdx - 1]);
  };

  async function dispatch() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/missions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          operator: form.operator,
          targetChannel: form.targetChannel,
          audienceProfile: form.audienceProfile,
          seedPersonaId: form.seedPersonaId,
          corroboratorPersonaIds: form.corroboratorPersonaIds,
          artifactPrompt: form.artifactPrompt,
        }),
      });
      const body = await res.json();
      if (!res.ok) {
        setError(body.error || `HTTP ${res.status}`);
      } else {
        setResult(body as DispatchResult);
        router.refresh();
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-[760px] max-w-[92vw] max-h-[88vh] flex flex-col border border-border-default bg-bg-panel shadow-2xl">
        <header className="flex items-baseline justify-between px-5 py-3 border-b border-border-default bg-bg-elevated shrink-0">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-classified">
              Mission dispatch
            </div>
            <h2 className="text-[15px] font-medium text-fg-default tracking-wide mt-[1px]">
              {result ? "Mission dispatched" : "New attack chain"}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="font-mono text-[11px] uppercase tracking-[0.14em] text-fg-faint hover:text-fg-default"
          >
            ✕ close
          </button>
        </header>

        {result ? (
          <DispatchedView
            result={result}
            seedName={seed?.name ?? form.seedPersonaId}
            corroboratorCount={form.corroboratorPersonaIds.length}
            onClose={onClose}
          />
        ) : (
          <>
            <Stepper current={step} />
            <div className="flex-1 min-h-0 overflow-y-auto px-5 py-4">
              {step === "target" && (
                <TargetStep
                  form={form}
                  channels={channels}
                  onChannelSelect={selectChannel}
                  onAudience={(v) =>
                    setForm((f) => ({ ...f, audienceProfile: v }))
                  }
                  onOperator={(v) =>
                    setForm((f) => ({ ...f, operator: v }))
                  }
                />
              )}
              {step === "persona" && (
                <PersonaStep
                  form={form}
                  personas={personas}
                  suggested={suggested}
                  seed={seed}
                  onSeedSelect={(id) =>
                    setForm((f) => ({ ...f, seedPersonaId: id }))
                  }
                  onToggleCorroborator={toggleCorroborator}
                />
              )}
              {step === "artifact" && (
                <ArtifactStep
                  prompt={form.artifactPrompt}
                  onChange={(v) =>
                    setForm((f) => ({ ...f, artifactPrompt: v }))
                  }
                />
              )}
              {step === "review" && (
                <ReviewStep
                  form={form}
                  channels={channels}
                  seed={seed}
                  corroborators={form.corroboratorPersonaIds
                    .map((id) => personasById.get(id))
                    .filter((p): p is PersonaLite => Boolean(p))}
                />
              )}
            </div>

            {error && (
              <div className="mx-5 mb-3 border border-fail-border bg-fail-bg/40 px-3 py-2 text-fail-fg text-[11px] font-mono">
                {error}
              </div>
            )}

            <footer className="px-5 py-3 border-t border-border-default bg-bg-elevated flex items-center justify-between shrink-0">
              <div className="font-mono text-[10px] text-fg-faint uppercase tracking-[0.14em]">
                Step {stepIdx + 1} / {STEPS.length} · {STEP_LABEL[step]}
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={back}
                  disabled={stepIdx === 0 || busy}
                  className="px-3 py-1 font-mono text-[11px] uppercase tracking-[0.14em] text-fg-muted hover:text-fg-default disabled:opacity-30 disabled:cursor-not-allowed"
                >
                  ← Back
                </button>
                {step === "review" ? (
                  <button
                    onClick={dispatch}
                    disabled={busy}
                    className="border border-info-border bg-info-bg hover:opacity-90 px-4 py-1 font-mono text-[11px] uppercase tracking-[0.16em] text-info-fg disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {busy ? "Dispatching…" : "Dispatch mission"}
                  </button>
                ) : (
                  <button
                    onClick={next}
                    disabled={!canAdvance[step]}
                    className="border border-info-border bg-info-bg hover:opacity-90 px-4 py-1 font-mono text-[11px] uppercase tracking-[0.16em] text-info-fg disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    Next →
                  </button>
                )}
              </div>
            </footer>
          </>
        )}
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────── */

function Stepper({ current }: { current: Step }) {
  return (
    <nav className="flex border-b border-border-subtle bg-bg-base shrink-0">
      {STEPS.map((s, i) => {
        const active = s === current;
        const done = STEPS.indexOf(current) > i;
        return (
          <div
            key={s}
            className={`flex-1 px-4 py-2 font-mono text-[10px] uppercase tracking-[0.16em] border-r border-border-subtle last:border-r-0 ${
              active
                ? "text-fg-default bg-bg-panel border-b-[2px] border-b-info-fg -mb-[1px]"
                : done
                  ? "text-pass-fg"
                  : "text-fg-faint"
            }`}
          >
            <span className="tabular-nums">{String(i + 1).padStart(2, "0")} </span>
            {STEP_LABEL[s]}
          </div>
        );
      })}
    </nav>
  );
}

function TargetStep({
  form,
  channels,
  onChannelSelect,
  onAudience,
  onOperator,
}: {
  form: { operator: string; targetChannel: string; audienceProfile: string };
  channels: Channel[];
  onChannelSelect: (id: string) => void;
  onAudience: (v: string) => void;
  onOperator: (v: string) => void;
}) {
  if (channels.length === 0) {
    return (
      <p className="text-fail-fg text-[12px]">
        No sandbox channels configured. Add one in /channels first.
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      <Field label="Sandbox channel" hint="Allowlist enforced.">
        <select
          value={form.targetChannel}
          onChange={(e) => onChannelSelect(e.target.value)}
          className="border border-border-default bg-bg-base px-3 py-2 font-mono text-[12px] text-fg-default focus:outline-none focus:border-info-fg"
        >
          {channels.map((c) => (
            <option key={c.id} value={c.id}>
              {c.displayName} ({c.id})
            </option>
          ))}
        </select>
      </Field>
      <Field
        label="Audience profile"
        hint="Auto-filled from selected channel; edit only if intent diverges."
      >
        <textarea
          rows={2}
          value={form.audienceProfile}
          onChange={(e) => onAudience(e.target.value)}
          className="border border-border-default bg-bg-base px-3 py-2 text-[12px] text-fg-default focus:outline-none focus:border-info-fg resize-none"
        />
      </Field>
      <Field label="Operator" hint="Recorded in the audit trail.">
        <input
          value={form.operator}
          onChange={(e) => onOperator(e.target.value)}
          className="border border-border-default bg-bg-base px-3 py-2 font-mono text-[12px] text-fg-default focus:outline-none focus:border-info-fg"
        />
      </Field>
    </div>
  );
}

function PersonaStep({
  form,
  personas,
  suggested,
  seed,
  onSeedSelect,
  onToggleCorroborator,
}: {
  form: { seedPersonaId: string; corroboratorPersonaIds: string[] };
  personas: PersonaLite[];
  suggested: PersonaLite[];
  seed: PersonaLite | undefined;
  onSeedSelect: (id: string) => void;
  onToggleCorroborator: (id: string) => void;
}) {
  if (personas.length === 0) {
    return (
      <p className="text-fail-fg text-[12px]">
        No personas in the library. Add one in social/personas/ first.
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      <Field
        label="Seed persona"
        hint="Posts the artifact first. Drives the cast pulled from its 'knows' graph."
      >
        <div className="grid grid-cols-2 gap-2">
          {personas.map((p) => {
            const active = p.id === form.seedPersonaId;
            return (
              <button
                key={p.id}
                onClick={() => onSeedSelect(p.id)}
                className={`text-left border px-3 py-2 hover:bg-bg-hover transition-colors ${
                  active
                    ? "border-info-fg bg-info-bg/30"
                    : "border-border-default bg-bg-base"
                }`}
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span className="text-[12px] text-fg-default">{p.name}</span>
                  <span className="font-mono text-[9px] text-fg-faint uppercase tracking-[0.14em]">
                    {p.language}
                  </span>
                </div>
                <div className="mt-[2px] text-[10px] text-fg-faint italic truncate">
                  {p.geoAnchor} · {p.bioShort}
                </div>
              </button>
            );
          })}
        </div>
      </Field>

      {seed && (
        <Field
          label={`Corroborators — pulled from ${seed.name}'s graph`}
          hint="Each will post a supporting message on a stagger after the seed lands."
        >
          {suggested.length === 0 ? (
            <p className="text-fg-faint italic text-[11px]">
              {seed.name} operates alone — no corroborators in the persona graph.
            </p>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              {suggested.map((p) => {
                const checked = form.corroboratorPersonaIds.includes(p.id);
                return (
                  <label
                    key={p.id}
                    className={`flex items-start gap-2 border px-3 py-2 cursor-pointer hover:bg-bg-hover transition-colors ${
                      checked
                        ? "border-pass-border bg-pass-bg/20"
                        : "border-border-default bg-bg-base"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => onToggleCorroborator(p.id)}
                      className="mt-1 accent-info-fg"
                    />
                    <span className="flex-1">
                      <span className="text-[12px] text-fg-default">{p.name}</span>
                      <span className="block text-[10px] text-fg-faint italic truncate">
                        {p.geoAnchor} · {p.language}
                      </span>
                    </span>
                  </label>
                );
              })}
            </div>
          )}
        </Field>
      )}
    </div>
  );
}

function ArtifactStep({
  prompt,
  onChange,
}: {
  prompt: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="flex flex-col gap-4">
      <Field
        label="Image prompt"
        hint="Persona-consistent, low-fidelity, plausible. Engine will run C2PA + Titan + SynthID against the output."
      >
        <textarea
          rows={5}
          value={prompt}
          onChange={(e) => onChange(e.target.value)}
          placeholder="e.g. leaked regiment movement order, smudged unit stamp, low-light phone photo"
          className="border border-border-default bg-bg-base px-3 py-2 text-[12px] text-fg-default focus:outline-none focus:border-info-fg resize-none"
        />
      </Field>
      <div className="border border-warn-border bg-warn-bg/20 px-3 py-2 text-[10px] text-warn-fg leading-5 font-mono">
        Sandbox enforcement — delivery.dry_run = true unconditionally.
      </div>
    </div>
  );
}

function ReviewStep({
  form,
  channels,
  seed,
  corroborators,
}: {
  form: { targetChannel: string; audienceProfile: string; artifactPrompt: string };
  channels: Channel[];
  seed: PersonaLite | undefined;
  corroborators: PersonaLite[];
}) {
  const channel = channels.find((c) => c.id === form.targetChannel);
  return (
    <div className="flex flex-col gap-4">
      <ReviewBlock label="Target">
        <ReviewRow label="Channel" value={channel?.displayName ?? form.targetChannel} mono />
        <ReviewRow label="Audience" value={form.audienceProfile} />
      </ReviewBlock>
      <ReviewBlock label="Cast">
        <ReviewRow label="Seed" value={seed ? `${seed.name} (${seed.id})` : "—"} mono />
        <ReviewRow
          label="Corroborators"
          value={
            corroborators.length === 0
              ? "(none — seed posts alone)"
              : corroborators.map((p) => p.name).join(", ")
          }
        />
      </ReviewBlock>
      <ReviewBlock label="Artifact">
        <p className="text-[12px] text-fg-default leading-6 whitespace-pre-wrap">
          {form.artifactPrompt}
        </p>
      </ReviewBlock>
      <p className="text-[10px] text-fg-faint italic leading-5">
        On dispatch: a YAML MissionSpec is emitted to{" "}
        <span className="font-mono text-fg-default">missions/inbox/</span> for
        the engine, and a campaign is opened on{" "}
        <span className="font-mono text-fg-default">/backstop</span> with the
        seed posted immediately and corroborators staggered behind it.
      </p>
    </div>
  );
}

function DispatchedView({
  result,
  seedName,
  corroboratorCount,
  onClose,
}: {
  result: DispatchResult;
  seedName: string;
  corroboratorCount: number;
  onClose: () => void;
}) {
  return (
    <div className="flex-1 min-h-0 overflow-y-auto px-5 py-6 flex flex-col gap-4">
      <div className="border border-pass-border bg-pass-bg/30 px-4 py-3">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-pass-fg">
          Dispatched
        </div>
        <div className="mt-1 font-mono text-[14px] text-fg-default tracking-wide">
          {result.missionId}
        </div>
        <div className="mt-2 text-[12px] text-fg-muted leading-6">
          {seedName} posted the seed. {corroboratorCount} corroborator
          {corroboratorCount === 1 ? "" : "s"} are scheduled to follow on a
          stagger.
        </div>
      </div>
      {result.campaignError && (
        <div className="border border-warn-border bg-warn-bg/20 px-3 py-2 text-warn-fg text-[11px] font-mono">
          Campaign write warning: {result.campaignError}
        </div>
      )}
      <div className="flex gap-2">
        <a
          href={`/backstop?c=${encodeURIComponent(result.campaignId)}`}
          className="border border-info-border bg-info-bg px-4 py-2 font-mono text-[11px] uppercase tracking-[0.16em] text-info-fg hover:opacity-90"
        >
          Open campaign
        </a>
        <a
          href={`/?m=${encodeURIComponent(result.missionId)}`}
          className="border border-border-default bg-bg-elevated px-4 py-2 font-mono text-[11px] uppercase tracking-[0.16em] text-fg-default hover:bg-bg-hover"
        >
          Mission record
        </a>
        <button
          onClick={onClose}
          className="font-mono text-[11px] uppercase tracking-[0.14em] text-fg-faint hover:text-fg-default px-3"
        >
          Close
        </button>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────── */

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-fg-faint">
        {label}
      </span>
      {children}
      {hint && (
        <span className="text-[10px] text-fg-faint italic">{hint}</span>
      )}
    </label>
  );
}

function ReviewBlock({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="border border-border-subtle bg-bg-base px-3 py-2">
      <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-fg-faint mb-2">
        {label}
      </div>
      {children}
    </div>
  );
}

function ReviewRow({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="grid grid-cols-[120px_1fr] gap-3 py-1 items-baseline">
      <dt className="text-fg-faint uppercase tracking-[0.14em] font-mono text-[10px]">
        {label}
      </dt>
      <dd className={`text-fg-muted text-[12px] ${mono ? "font-mono" : ""}`}>
        {value}
      </dd>
    </div>
  );
}
