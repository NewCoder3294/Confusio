"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

type Snapshot = Record<string, { set: boolean; preview: string }>;

type Provider = {
  id: string;
  title: string;
  blurb: string;
  fields: Array<{
    key: string;
    label: string;
    hint?: string;
    placeholder?: string;
    multiline?: boolean;
    type?: "text" | "password";
  }>;
  status: "wired" | "ui-only";
};

const PROVIDERS: Provider[] = [
  {
    id: "openai",
    title: "OpenAI",
    blurb:
      "Backs the persona LLM that drafts seed posts and corroborator replies.",
    status: "wired",
    fields: [
      {
        key: "OPENAI_API_KEY",
        label: "API key",
        type: "password",
        placeholder: "sk-…",
        hint: "Used by social/llm.py at runtime.",
      },
    ],
  },
  {
    id: "telegram",
    title: "Telegram (Telethon)",
    blurb:
      "Each persona owns a .session file. Telethon authenticates with these app credentials before a session is forged.",
    status: "wired",
    fields: [
      {
        key: "TELEGRAM_API_ID",
        label: "API ID",
        placeholder: "1234567",
        hint: "Numeric — from my.telegram.org.",
      },
      {
        key: "TELEGRAM_API_HASH",
        label: "API hash",
        type: "password",
        placeholder: "32 hex chars",
      },
      {
        key: "OPERATOR_USER_ID",
        label: "Operator user id",
        placeholder: "Telegram user id",
        hint: "Recorded on every approval action in the audit trail.",
      },
    ],
  },
];

export function SettingsForm({
  initial,
  envPath,
}: {
  initial: Snapshot;
  envPath: string;
}) {
  const router = useRouter();
  const [snapshot, setSnapshot] = useState<Snapshot>(initial);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busyProvider, setBusyProvider] = useState<string | null>(null);
  const [error, setError] = useState<{
    providerId: string;
    message: string;
  } | null>(null);
  const [savedProvider, setSavedProvider] = useState<string | null>(null);

  function setField(k: string, v: string) {
    setDrafts((d) => ({ ...d, [k]: v }));
    setSavedProvider(null);
    setError(null);
  }

  function clearProviderDrafts(p: Provider) {
    setDrafts((d) => {
      const next = { ...d };
      for (const f of p.fields) delete next[f.key];
      return next;
    });
  }

  async function saveProvider(p: Provider) {
    const updates: Record<string, string> = {};
    for (const f of p.fields) {
      if (Object.prototype.hasOwnProperty.call(drafts, f.key)) {
        updates[f.key] = drafts[f.key];
      }
    }
    if (Object.keys(updates).length === 0) return;
    setBusyProvider(p.id);
    setError(null);
    try {
      const res = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updates),
      });
      const body = await res.json();
      if (!res.ok) {
        setError({ providerId: p.id, message: body.error || `HTTP ${res.status}` });
        return;
      }
      setSnapshot(body.settings as Snapshot);
      clearProviderDrafts(p);
      setSavedProvider(p.id);
      router.refresh();
    } catch (e) {
      setError({ providerId: p.id, message: (e as Error).message });
    } finally {
      setBusyProvider(null);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="border border-border-subtle bg-bg-base px-4 py-2 text-[11px] font-mono text-fg-faint">
        Storage ·{" "}
        <span className="text-fg-default">{envPath}</span> · permissions 600,
        gitignored. Saved values are never echoed back — fields below show only
        a masked preview.
      </div>

      {PROVIDERS.map((p) => (
        <ProviderCard
          key={p.id}
          provider={p}
          snapshot={snapshot}
          drafts={drafts}
          onField={setField}
          onSave={() => saveProvider(p)}
          onCancel={() => clearProviderDrafts(p)}
          busy={busyProvider === p.id}
          saved={savedProvider === p.id}
          error={error?.providerId === p.id ? error.message : null}
        />
      ))}
    </div>
  );
}

function ProviderCard({
  provider,
  snapshot,
  drafts,
  onField,
  onSave,
  onCancel,
  busy,
  saved,
  error,
}: {
  provider: Provider;
  snapshot: Snapshot;
  drafts: Record<string, string>;
  onField: (k: string, v: string) => void;
  onSave: () => void;
  onCancel: () => void;
  busy: boolean;
  saved: boolean;
  error: string | null;
}) {
  const dirty = provider.fields.some((f) =>
    Object.prototype.hasOwnProperty.call(drafts, f.key),
  );

  return (
    <section className="border border-border-default bg-bg-panel">
      <header className="flex items-baseline justify-between gap-3 px-4 py-2 border-b border-border-default bg-bg-elevated">
        <div>
          <h2 className="text-[14px] text-fg-default tracking-wide font-medium uppercase">
            {provider.title}
          </h2>
          <p className="mt-[1px] text-[11px] text-fg-muted leading-5 max-w-[700px]">
            {provider.blurb}
          </p>
        </div>
        <span
          className={`font-mono text-[10px] uppercase tracking-[0.16em] px-2 py-[2px] border ${
            provider.status === "wired"
              ? "text-pass-fg border-pass-border bg-pass-bg/30"
              : "text-warn-fg border-warn-border bg-warn-bg/30"
          }`}
        >
          {provider.status === "wired" ? "Wired" : "UI-only"}
        </span>
      </header>

      <div className="px-4 py-3 flex flex-col gap-3">
        {provider.fields.map((f) => {
          const cur = snapshot[f.key];
          const draft = drafts[f.key];
          const editing = draft !== undefined;
          return (
            <div key={f.key} className="flex flex-col gap-1">
              <div className="flex items-baseline justify-between">
                <label
                  htmlFor={`field-${f.key}`}
                  className="font-mono text-[10px] uppercase tracking-[0.14em] text-fg-faint"
                >
                  {f.label}
                </label>
                <span className="font-mono text-[9px] text-fg-faint">
                  {f.key}
                </span>
              </div>
              <input
                id={`field-${f.key}`}
                type={f.type === "password" && !editing ? "password" : "text"}
                autoComplete="off"
                spellCheck={false}
                value={editing ? draft : cur?.preview ?? ""}
                onChange={(e) => onField(f.key, e.target.value)}
                onFocus={(e) => {
                  // First focus on a field with an existing value — start
                  // editing with empty draft, don't expose the masked text.
                  if (!editing && cur?.set) {
                    onField(f.key, "");
                    e.currentTarget.select();
                  }
                }}
                placeholder={f.placeholder}
                className="border border-border-default bg-bg-base px-3 py-2 font-mono text-[12px] text-fg-default focus:outline-none focus:border-info-fg"
              />
              <div className="flex items-baseline justify-between">
                <span className="text-[10px] text-fg-faint italic">
                  {f.hint || ""}
                </span>
                <span className="font-mono text-[9px] text-fg-faint">
                  {editing
                    ? draft.length === 0
                      ? "will clear"
                      : "draft"
                    : cur?.set
                      ? "set"
                      : "unset"}
                </span>
              </div>
            </div>
          );
        })}

        {error && (
          <div className="border border-fail-border bg-fail-bg/40 px-3 py-2 text-fail-fg text-[11px] font-mono">
            {error}
          </div>
        )}
        {saved && !dirty && (
          <div className="border border-pass-border bg-pass-bg/30 px-3 py-2 text-pass-fg text-[11px] font-mono">
            Saved.
          </div>
        )}

        <div className="flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={!dirty || busy}
            className="px-3 py-1 font-mono text-[11px] uppercase tracking-[0.14em] text-fg-muted hover:text-fg-default disabled:opacity-30 disabled:cursor-not-allowed"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onSave}
            disabled={!dirty || busy}
            className="border border-info-border bg-info-bg hover:opacity-90 px-4 py-1 font-mono text-[11px] uppercase tracking-[0.16em] text-info-fg disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {busy ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </section>
  );
}
