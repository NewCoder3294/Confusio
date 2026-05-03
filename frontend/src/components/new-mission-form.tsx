"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

type Channel = {
  id: string;
  displayName: string;
  audienceProfile: string;
};

type Result = {
  ok: true;
  missionId: string;
  inboxPath: string;
};

export function NewMissionForm({ sandboxChannels }: { sandboxChannels: Channel[] }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Result | null>(null);

  const [form, setForm] = useState({
    missionId: "",
    operator: "J2-INSCOM-Demo",
    targetChannel: sandboxChannels[0]?.id ?? "",
    audienceProfile: sandboxChannels[0]?.audienceProfile ?? "",
    personaArchetype: "",
    personaNameSeed: "",
    artifactPrompt: "",
  });

  function setField<K extends keyof typeof form>(k: K, v: (typeof form)[K]) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  function selectChannel(id: string) {
    const c = sandboxChannels.find((c) => c.id === id);
    setForm((f) => ({
      ...f,
      targetChannel: id,
      audienceProfile: c?.audienceProfile ?? f.audienceProfile,
    }));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch("/api/missions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      const body = await res.json();
      if (!res.ok) {
        setError(body.error || `HTTP ${res.status}`);
      } else {
        setResult(body as Result);
        router.refresh();
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (result) {
    return (
      <div className="border border-pass-border bg-pass-bg/40 p-6 flex flex-col gap-4">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-pass-fg">
            Mission dispatched
          </div>
          <h2 className="mt-1 text-xl text-fg-default font-medium tracking-wide">
            {result.missionId}
          </h2>
          <p className="mt-2 text-[13px] text-fg-muted leading-6">
            Spec written to{" "}
            <span className="font-mono text-fg-mono">{result.inboxPath}</span>.
            The engine watches this directory; the mission will appear on the
            Mission Board with status{" "}
            <span className="font-mono text-info-fg">executing</span> within
            seconds, then propagate to{" "}
            <span className="font-mono text-pass-fg">completed</span> when the
            engine finishes.
          </p>
        </div>
        <div className="flex gap-2">
          <Link
            href={`/?m=${encodeURIComponent(result.missionId)}`}
            className="border border-info-border bg-info-bg px-4 py-2 font-mono text-[12px] uppercase tracking-[0.16em] text-info-fg hover:opacity-90"
          >
            Open mission record
          </Link>
          <button
            onClick={() => {
              setResult(null);
              setForm((f) => ({
                ...f,
                missionId: "",
                personaArchetype: "",
                personaNameSeed: "",
                artifactPrompt: "",
              }));
            }}
            className="border border-border-default bg-bg-elevated px-4 py-2 font-mono text-[12px] uppercase tracking-[0.16em] text-fg-default hover:bg-bg-hover"
          >
            Dispatch another
          </button>
        </div>
      </div>
    );
  }

  return (
    <form
      onSubmit={submit}
      className="border border-border-subtle bg-bg-panel p-6 flex flex-col gap-5"
    >
      <Section title="Identity">
        <div className="grid grid-cols-2 gap-4">
          <Field
            label="Mission ID"
            hint="Leave blank to auto-generate (SHADOW-FOX-XXXXXX)."
          >
            <input
              autoComplete="off"
              value={form.missionId}
              onChange={(e) => setField("missionId", e.target.value.trim())}
              placeholder="(auto)"
              className="border border-border-default bg-bg-base px-3 py-2 font-mono text-[12px] text-fg-default focus:outline-none focus:border-info-fg"
            />
          </Field>
          <Field label="Operator" hint="Recorded in the audit trail.">
            <input
              required
              value={form.operator}
              onChange={(e) => setField("operator", e.target.value)}
              className="border border-border-default bg-bg-base px-3 py-2 font-mono text-[12px] text-fg-default focus:outline-none focus:border-info-fg"
            />
          </Field>
        </div>
      </Section>

      <Section title="Target">
        <Field
          label="Sandbox channel"
          hint="Allowlist enforced — non-sandbox channels are not selectable."
        >
          {sandboxChannels.length === 0 ? (
            <div className="border border-fail-border bg-fail-bg/40 px-3 py-2 text-fail-fg text-[12px]">
              No sandbox channels configured. Add one in{" "}
              <Link href="/channels" className="underline">
                /channels
              </Link>{" "}
              first.
            </div>
          ) : (
            <select
              required
              value={form.targetChannel}
              onChange={(e) => selectChannel(e.target.value)}
              className="border border-border-default bg-bg-base px-3 py-2 font-mono text-[12px] text-fg-default focus:outline-none focus:border-info-fg"
            >
              {sandboxChannels.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.displayName} ({c.id})
                </option>
              ))}
            </select>
          )}
        </Field>
        <Field
          label="Audience profile"
          hint="Auto-filled from selected channel; edit only if intent diverges."
        >
          <textarea
            required
            rows={2}
            value={form.audienceProfile}
            onChange={(e) => setField("audienceProfile", e.target.value)}
            className="border border-border-default bg-bg-base px-3 py-2 text-[12px] text-fg-default focus:outline-none focus:border-info-fg resize-none"
          />
        </Field>
      </Section>

      <Section title="Persona">
        <div className="grid grid-cols-2 gap-4">
          <Field
            label="Archetype"
            hint="Operational role + posture. Drives voice, vocabulary, posting cadence."
          >
            <input
              required
              value={form.personaArchetype}
              onChange={(e) => setField("personaArchetype", e.target.value)}
              placeholder="e.g. battalion-quartermaster-frustrated"
              className="border border-border-default bg-bg-base px-3 py-2 text-[12px] text-fg-default focus:outline-none focus:border-info-fg"
            />
          </Field>
          <Field label="Name seed" hint="Plausible operational alias.">
            <input
              value={form.personaNameSeed}
              onChange={(e) => setField("personaNameSeed", e.target.value)}
              placeholder="e.g. Sasha P."
              className="border border-border-default bg-bg-base px-3 py-2 text-[12px] text-fg-default focus:outline-none focus:border-info-fg"
            />
          </Field>
        </div>
      </Section>

      <Section title="Artifact">
        <Field
          label="Image prompt"
          hint="Persona-consistent, low-fidelity, plausible. Engine will run C2PA + Titan + SynthID against the output."
        >
          <textarea
            required
            rows={3}
            value={form.artifactPrompt}
            onChange={(e) => setField("artifactPrompt", e.target.value)}
            placeholder="leaked regiment movement order, smudged unit stamp, low-light phone photo"
            className="border border-border-default bg-bg-base px-3 py-2 text-[12px] text-fg-default focus:outline-none focus:border-info-fg resize-none"
          />
        </Field>
      </Section>

      <div className="border border-warn-border bg-warn-bg/30 px-4 py-3 text-[11px] text-warn-fg leading-5">
        <div className="font-mono uppercase tracking-[0.14em] text-[10px] mb-1">
          Sandbox enforcement
        </div>
        Dispatched with{" "}
        <span className="font-mono">delivery.dry_run = true</span>{" "}
        unconditionally. Live delivery requires an out-of-band engine flag and
        is not toggleable from this UI.
      </div>

      {error && (
        <div className="border border-fail-border bg-fail-bg px-4 py-3 text-fail-fg text-[12px] font-mono">
          {error}
        </div>
      )}

      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={busy || sandboxChannels.length === 0}
          className="border border-info-border bg-info-bg hover:opacity-90 px-5 py-2 font-mono text-[12px] uppercase tracking-[0.16em] text-info-fg disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {busy ? "Dispatching…" : "Dispatch mission"}
        </button>
        <Link
          href="/"
          className="font-mono text-[11px] uppercase tracking-[0.14em] text-fg-faint hover:text-fg-default"
        >
          Cancel
        </Link>
      </div>
    </form>
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
    <fieldset className="flex flex-col gap-3 border-t border-border-subtle pt-4 first:border-t-0 first:pt-0">
      <legend className="font-mono text-[11px] uppercase tracking-[0.18em] text-fg-faint">
        {title}
      </legend>
      {children}
    </fieldset>
  );
}

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
