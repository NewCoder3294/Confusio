"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export function NewChannelForm() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    channel_id: "",
    displayName: "",
    audienceProfile: "",
  });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await fetch("/api/channels", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...form, platform: "telegram" }),
      });
      const body = await res.json();
      if (!res.ok) {
        setError(body.error || `HTTP ${res.status}`);
      } else {
        setSuccess(`Channel ${body.channel.channel_id} created. Refreshing…`);
        setForm({ channel_id: "", displayName: "", audienceProfile: "" });
        // Server-side revalidation already invalidated /channels;
        // bounce the router cache.
        router.refresh();
        setTimeout(() => setOpen(false), 600);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="border border-border-default bg-bg-elevated hover:bg-bg-hover px-4 py-2 font-mono text-[11px] uppercase tracking-[0.16em] text-fg-default"
      >
        + Add sandbox channel
      </button>
    );
  }

  return (
    <form
      onSubmit={submit}
      className="border border-border-default bg-bg-panel p-4 flex flex-col gap-3"
    >
      <div className="flex items-baseline justify-between">
        <h3 className="font-mono text-[11px] uppercase tracking-[0.18em] text-fg-faint">
          New sandbox channel
        </h3>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="font-mono text-[10px] text-fg-faint hover:text-fg-default uppercase tracking-[0.14em]"
        >
          Cancel
        </button>
      </div>

      <Field
        label="Channel ID"
        hint="Snake_case identifier, 3–40 chars. PK in Foundry."
      >
        <input
          required
          autoComplete="off"
          pattern="[a-zA-Z0-9_]{3,40}"
          value={form.channel_id}
          onChange={(e) =>
            setForm((f) => ({ ...f, channel_id: e.target.value.trim() }))
          }
          placeholder="e.g. inscom_sandbox_bravo"
          className="border border-border-default bg-bg-base px-3 py-2 font-mono text-[12px] text-fg-default focus:outline-none focus:border-info-fg"
        />
      </Field>

      <Field
        label="Display name"
        hint="Operator-facing label. Convention: @handle for Telegram."
      >
        <input
          required
          value={form.displayName}
          onChange={(e) => setForm((f) => ({ ...f, displayName: e.target.value }))}
          placeholder="e.g. @inscom_sandbox_bravo"
          className="border border-border-default bg-bg-base px-3 py-2 text-[12px] text-fg-default focus:outline-none focus:border-info-fg"
        />
      </Field>

      <Field
        label="Audience profile"
        hint="One-line target audience. Used by the planner to constrain persona / language."
      >
        <textarea
          required
          rows={2}
          value={form.audienceProfile}
          onChange={(e) =>
            setForm((f) => ({ ...f, audienceProfile: e.target.value }))
          }
          placeholder="e.g. Russian-speaking, regional supply NCOs, mid-30s"
          className="border border-border-default bg-bg-base px-3 py-2 text-[12px] text-fg-default focus:outline-none focus:border-info-fg resize-none"
        />
      </Field>

      <div className="border border-warn-border bg-warn-bg/30 px-3 py-2">
        <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-warn-fg mb-1">
          Sandbox enforcement
        </div>
        <p className="text-[11px] text-warn-fg leading-5">
          New channels are created with{" "}
          <span className="font-mono">isSandbox=true</span> unconditionally.
          Promoting a channel to non-sandbox requires out-of-band legal review
          (J2 + OGC) and is performed in Foundry directly, not from this UI.
        </p>
      </div>

      {error && (
        <div className="border border-fail-border bg-fail-bg px-3 py-2 text-fail-fg text-[12px] font-mono">
          {error}
        </div>
      )}
      {success && (
        <div className="border border-pass-border bg-pass-bg px-3 py-2 text-pass-fg text-[12px] font-mono">
          {success}
        </div>
      )}

      <button
        type="submit"
        disabled={busy}
        className="border border-info-border bg-info-bg hover:opacity-90 px-4 py-2 font-mono text-[12px] uppercase tracking-[0.16em] text-info-fg disabled:opacity-50 disabled:cursor-wait"
      >
        {busy ? "Creating…" : "Create channel"}
      </button>
    </form>
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
      {hint && <span className="text-[10px] text-fg-faint italic">{hint}</span>}
    </label>
  );
}
