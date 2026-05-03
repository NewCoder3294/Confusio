"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

type AgentLite = {
  id: string;
  name: string;
  language: string;
  geoAnchor: string;
};

type Step = "identity" | "voice" | "network" | "review";

const STEPS: Step[] = ["identity", "voice", "network", "review"];
const STEP_LABEL: Record<Step, string> = {
  identity: "Identity",
  voice: "Voice",
  network: "Network",
  review: "Review",
};

type FormState = {
  id: string;
  name: string;
  language: string;
  geoAnchor: string;
  bioShort: string;
  backstory: string;
  style: string;
  vocabularyQuirks: string;
  topicFocus: string;
  examples: string;
  activeStart: number;
  activeEnd: number;
  avgPostsPerDay: number;
  knows: string[];
};

const INITIAL: FormState = {
  id: "",
  name: "",
  language: "ru",
  geoAnchor: "",
  bioShort: "",
  backstory: "",
  style: "",
  vocabularyQuirks: "",
  topicFocus: "",
  examples: "",
  activeStart: 7,
  activeEnd: 22,
  avgPostsPerDay: 3,
  knows: [],
};

function splitLines(s: string): string[] {
  return s
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l.length > 0);
}

function splitChips(s: string): string[] {
  return s
    .split(/[,\n]/)
    .map((l) => l.trim())
    .filter((l) => l.length > 0);
}

export function NewAgentModal({
  agents,
  open,
  onClose,
}: {
  agents: AgentLite[];
  open: boolean;
  onClose: () => void;
}) {
  const router = useRouter();
  const [step, setStep] = useState<Step>("identity");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [createdId, setCreatedId] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(INITIAL);

  // Reset on open
  useEffect(() => {
    if (open) {
      setStep("identity");
      setError(null);
      setCreatedId(null);
      setForm(INITIAL);
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

  const idValid = /^[a-z0-9_]{3,40}$/.test(form.id);
  const idTaken = agents.some((a) => a.id === form.id);

  const canAdvance: Record<Step, boolean> = {
    identity: Boolean(
      idValid &&
        !idTaken &&
        form.name.trim() &&
        form.language.trim() &&
        form.geoAnchor.trim() &&
        form.bioShort.trim(),
    ),
    voice: Boolean(form.backstory.trim() && form.style.trim()),
    network:
      form.activeStart >= 0 &&
      form.activeEnd <= 24 &&
      form.activeStart < form.activeEnd &&
      form.avgPostsPerDay >= 0 &&
      form.avgPostsPerDay <= 96,
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

  const knowsSet = useMemo(() => new Set(form.knows), [form.knows]);
  function toggleKnow(id: string) {
    setForm((f) => ({
      ...f,
      knows: f.knows.includes(id)
        ? f.knows.filter((x) => x !== id)
        : [...f.knows, id],
    }));
  }

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/personas", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id: form.id,
          name: form.name.trim(),
          language: form.language.trim(),
          geo_anchor: form.geoAnchor.trim(),
          bio_short: form.bioShort.trim(),
          backstory: form.backstory.trim(),
          style: form.style.trim(),
          vocabulary_quirks: splitChips(form.vocabularyQuirks),
          topic_focus: splitChips(form.topicFocus),
          examples: splitLines(form.examples),
          knows: form.knows,
          posting_schedule: {
            active_hours_local: [form.activeStart, form.activeEnd],
            avg_posts_per_day: form.avgPostsPerDay,
          },
        }),
      });
      const body = await res.json();
      if (!res.ok) {
        setError(body.error || `HTTP ${res.status}`);
      } else {
        setCreatedId(body.agent?.id ?? form.id);
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
              Agent forge
            </div>
            <h2 className="text-[15px] font-medium text-fg-default tracking-wide mt-[1px]">
              {createdId ? "Agent created" : "Fabricate new agent"}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="font-mono text-[11px] uppercase tracking-[0.14em] text-fg-faint hover:text-fg-default"
          >
            ✕ close
          </button>
        </header>

        {createdId ? (
          <CreatedView agentId={createdId} onClose={onClose} />
        ) : (
          <>
            <Stepper current={step} />
            <div className="flex-1 min-h-0 overflow-y-auto px-5 py-4">
              {step === "identity" && (
                <IdentityStep
                  form={form}
                  setForm={setForm}
                  idValid={idValid}
                  idTaken={idTaken}
                />
              )}
              {step === "voice" && (
                <VoiceStep form={form} setForm={setForm} />
              )}
              {step === "network" && (
                <NetworkStep
                  form={form}
                  setForm={setForm}
                  agents={agents}
                  knowsSet={knowsSet}
                  onToggleKnow={toggleKnow}
                />
              )}
              {step === "review" && (
                <ReviewStep form={form} agents={agents} />
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
                    onClick={submit}
                    disabled={busy}
                    className="border border-info-border bg-info-bg hover:opacity-90 px-4 py-1 font-mono text-[11px] uppercase tracking-[0.16em] text-info-fg disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {busy ? "Creating…" : "Create agent"}
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

function IdentityStep({
  form,
  setForm,
  idValid,
  idTaken,
}: {
  form: FormState;
  setForm: React.Dispatch<React.SetStateAction<FormState>>;
  idValid: boolean;
  idTaken: boolean;
}) {
  const idHint = !form.id
    ? "Snake_case identifier — locks in file path social/personas/<id>.json."
    : !idValid
      ? "Invalid: 3–40 chars, lowercase letters / digits / underscore only."
      : idTaken
        ? "Taken — pick a different id."
        : "Looks good.";
  const idTone = !form.id || idValid && !idTaken ? "fg-faint" : "fail-fg";

  return (
    <div className="flex flex-col gap-4">
      <Field label="Agent ID" hint={idHint} hintTone={idTone}>
        <input
          autoComplete="off"
          spellCheck={false}
          value={form.id}
          onChange={(e) =>
            setForm((f) => ({
              ...f,
              id: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ""),
            }))
          }
          placeholder="e.g. ivan_kh"
          className="border border-border-default bg-bg-base px-3 py-2 font-mono text-[12px] text-fg-default focus:outline-none focus:border-info-fg"
        />
      </Field>
      <Field label="Display name" hint="Operator-facing name.">
        <input
          value={form.name}
          onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
          placeholder="e.g. Ivan"
          className="border border-border-default bg-bg-base px-3 py-2 text-[12px] text-fg-default focus:outline-none focus:border-info-fg"
        />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Language" hint="ISO 639-1, e.g. ru, uk, en.">
          <input
            value={form.language}
            onChange={(e) =>
              setForm((f) => ({
                ...f,
                language: e.target.value.toLowerCase().slice(0, 8),
              }))
            }
            className="border border-border-default bg-bg-base px-3 py-2 font-mono text-[12px] text-fg-default focus:outline-none focus:border-info-fg"
          />
        </Field>
        <Field label="Geo anchor" hint="Where this identity appears to live.">
          <input
            value={form.geoAnchor}
            onChange={(e) =>
              setForm((f) => ({ ...f, geoAnchor: e.target.value }))
            }
            placeholder="e.g. Kharkiv, UA"
            className="border border-border-default bg-bg-base px-3 py-2 text-[12px] text-fg-default focus:outline-none focus:border-info-fg"
          />
        </Field>
      </div>
      <Field
        label="Short bio"
        hint="One line — the listing summary visible in the roster."
      >
        <input
          value={form.bioShort}
          onChange={(e) =>
            setForm((f) => ({ ...f, bioShort: e.target.value }))
          }
          placeholder="e.g. Delivery driver, posts what he sees on his routes"
          className="border border-border-default bg-bg-base px-3 py-2 text-[12px] text-fg-default focus:outline-none focus:border-info-fg"
        />
      </Field>
    </div>
  );
}

function VoiceStep({
  form,
  setForm,
}: {
  form: FormState;
  setForm: React.Dispatch<React.SetStateAction<FormState>>;
}) {
  return (
    <div className="flex flex-col gap-4">
      <Field
        label="Backstory"
        hint="Age, job, household, why this account exists. Drives the LLM voice."
      >
        <textarea
          rows={4}
          value={form.backstory}
          onChange={(e) =>
            setForm((f) => ({ ...f, backstory: e.target.value }))
          }
          className="border border-border-default bg-bg-base px-3 py-2 text-[12px] text-fg-default focus:outline-none focus:border-info-fg resize-none"
        />
      </Field>
      <Field
        label="Style"
        hint="Voice rules — tone, punctuation, sentence length, register."
      >
        <textarea
          rows={3}
          value={form.style}
          onChange={(e) => setForm((f) => ({ ...f, style: e.target.value }))}
          className="border border-border-default bg-bg-base px-3 py-2 text-[12px] text-fg-default focus:outline-none focus:border-info-fg resize-none"
        />
      </Field>
      <Field
        label="Vocabulary quirks"
        hint="Comma- or newline-separated. Catchphrases, fillers, abbreviations."
      >
        <textarea
          rows={2}
          value={form.vocabularyQuirks}
          onChange={(e) =>
            setForm((f) => ({ ...f, vocabularyQuirks: e.target.value }))
          }
          placeholder="короче, блин, ну, abbreviates locations"
          className="border border-border-default bg-bg-base px-3 py-2 text-[12px] text-fg-default focus:outline-none focus:border-info-fg resize-none"
        />
      </Field>
      <Field
        label="Topic focus"
        hint="Comma- or newline-separated. What this agent posts about."
      >
        <textarea
          rows={2}
          value={form.topicFocus}
          onChange={(e) =>
            setForm((f) => ({ ...f, topicFocus: e.target.value }))
          }
          placeholder="traffic, sirens, neighborhood incidents"
          className="border border-border-default bg-bg-base px-3 py-2 text-[12px] text-fg-default focus:outline-none focus:border-info-fg resize-none"
        />
      </Field>
      <Field
        label="Sample posts"
        hint="One per line. Few-shot examples for the LLM. Match the style above."
      >
        <textarea
          rows={5}
          value={form.examples}
          onChange={(e) =>
            setForm((f) => ({ ...f, examples: e.target.value }))
          }
          placeholder={"видел колонну на М-04\nопять воет сирена. уже привык"}
          className="border border-border-default bg-bg-base px-3 py-2 text-[12px] text-fg-default focus:outline-none focus:border-info-fg resize-none"
        />
      </Field>
    </div>
  );
}

function NetworkStep({
  form,
  setForm,
  agents,
  knowsSet,
  onToggleKnow,
}: {
  form: FormState;
  setForm: React.Dispatch<React.SetStateAction<FormState>>;
  agents: AgentLite[];
  knowsSet: Set<string>;
  onToggleKnow: (id: string) => void;
}) {
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-3 gap-3">
        <Field label="Active hours start" hint="0–23 local.">
          <input
            type="number"
            min={0}
            max={23}
            value={form.activeStart}
            onChange={(e) =>
              setForm((f) => ({
                ...f,
                activeStart: Math.max(0, Math.min(23, Number(e.target.value))),
              }))
            }
            className="border border-border-default bg-bg-base px-3 py-2 font-mono text-[12px] text-fg-default focus:outline-none focus:border-info-fg"
          />
        </Field>
        <Field label="Active hours end" hint="1–24 local, > start.">
          <input
            type="number"
            min={1}
            max={24}
            value={form.activeEnd}
            onChange={(e) =>
              setForm((f) => ({
                ...f,
                activeEnd: Math.max(1, Math.min(24, Number(e.target.value))),
              }))
            }
            className="border border-border-default bg-bg-base px-3 py-2 font-mono text-[12px] text-fg-default focus:outline-none focus:border-info-fg"
          />
        </Field>
        <Field label="Posts per day" hint="Average. 0–96.">
          <input
            type="number"
            min={0}
            max={96}
            value={form.avgPostsPerDay}
            onChange={(e) =>
              setForm((f) => ({
                ...f,
                avgPostsPerDay: Math.max(
                  0,
                  Math.min(96, Number(e.target.value)),
                ),
              }))
            }
            className="border border-border-default bg-bg-base px-3 py-2 font-mono text-[12px] text-fg-default focus:outline-none focus:border-info-fg"
          />
        </Field>
      </div>

      <Field
        label="Knows"
        hint="Other agents this one corroborates with after a seed lands."
      >
        {agents.length === 0 ? (
          <p className="text-fg-faint italic text-[11px]">
            No other agents in the library yet.
          </p>
        ) : (
          <div className="grid grid-cols-2 gap-2">
            {agents.map((a) => {
              const checked = knowsSet.has(a.id);
              return (
                <label
                  key={a.id}
                  className={`flex items-start gap-2 border px-3 py-2 cursor-pointer hover:bg-bg-hover transition-colors ${
                    checked
                      ? "border-pass-border bg-pass-bg/20"
                      : "border-border-default bg-bg-base"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => onToggleKnow(a.id)}
                    className="mt-1 accent-info-fg"
                  />
                  <span className="flex-1">
                    <span className="text-[12px] text-fg-default">{a.name}</span>
                    <span className="block text-[10px] text-fg-faint italic truncate">
                      {a.geoAnchor} · {a.language}
                    </span>
                  </span>
                </label>
              );
            })}
          </div>
        )}
      </Field>
    </div>
  );
}

function ReviewStep({
  form,
  agents,
}: {
  form: FormState;
  agents: AgentLite[];
}) {
  const knowsNames = form.knows
    .map((id) => agents.find((a) => a.id === id)?.name ?? id)
    .join(", ");
  return (
    <div className="flex flex-col gap-4">
      <ReviewBlock label="Identity">
        <ReviewRow label="ID" value={form.id} mono />
        <ReviewRow label="Name" value={form.name} />
        <ReviewRow label="Language" value={form.language} mono />
        <ReviewRow label="Geo" value={form.geoAnchor} />
        <ReviewRow label="Bio" value={form.bioShort} />
      </ReviewBlock>
      <ReviewBlock label="Voice">
        <ReviewRow label="Backstory" value={form.backstory} />
        <ReviewRow label="Style" value={form.style} />
        <ReviewRow
          label="Quirks"
          value={splitChips(form.vocabularyQuirks).join(", ") || "—"}
        />
        <ReviewRow
          label="Topics"
          value={splitChips(form.topicFocus).join(", ") || "—"}
        />
        <ReviewRow
          label="Examples"
          value={`${splitLines(form.examples).length} sample(s)`}
          mono
        />
      </ReviewBlock>
      <ReviewBlock label="Cadence & network">
        <ReviewRow
          label="Active hours"
          value={`${String(form.activeStart).padStart(2, "0")}–${String(form.activeEnd).padStart(2, "0")} local`}
          mono
        />
        <ReviewRow
          label="Posts/day"
          value={String(form.avgPostsPerDay)}
          mono
        />
        <ReviewRow label="Knows" value={knowsNames || "(operates alone)"} />
      </ReviewBlock>
      <p className="text-[10px] text-fg-faint italic leading-5">
        On create: a JSON file is written to{" "}
        <span className="font-mono text-fg-default">
          social/personas/{form.id}.json
        </span>
        . The engine picks it up on its next persona-library reload.
      </p>
    </div>
  );
}

function CreatedView({
  agentId,
  onClose,
}: {
  agentId: string;
  onClose: () => void;
}) {
  return (
    <div className="flex-1 min-h-0 overflow-y-auto px-5 py-6 flex flex-col gap-4">
      <div className="border border-pass-border bg-pass-bg/30 px-4 py-3">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-pass-fg">
          Created
        </div>
        <div className="mt-1 font-mono text-[14px] text-fg-default tracking-wide">
          {agentId}
        </div>
        <div className="mt-2 text-[12px] text-fg-muted leading-6">
          Persona file written. The roster has been refreshed.
        </div>
      </div>
      <div className="flex gap-2">
        <a
          href={`/personas?p=${encodeURIComponent(agentId)}`}
          className="border border-info-border bg-info-bg px-4 py-2 font-mono text-[11px] uppercase tracking-[0.16em] text-info-fg hover:opacity-90"
        >
          Open agent
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
  hintTone = "fg-faint",
  children,
}: {
  label: string;
  hint?: string;
  hintTone?: "fg-faint" | "fail-fg";
  children: React.ReactNode;
}) {
  const hintClass =
    hintTone === "fail-fg" ? "text-fail-fg" : "text-fg-faint italic";
  return (
    <label className="flex flex-col gap-1">
      <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-fg-faint">
        {label}
      </span>
      {children}
      {hint && <span className={`text-[10px] ${hintClass}`}>{hint}</span>}
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
      <dd
        className={`text-fg-muted text-[12px] whitespace-pre-wrap ${mono ? "font-mono" : ""}`}
      >
        {value || "—"}
      </dd>
    </div>
  );
}
