"use client";

import { useState, type ReactNode } from "react";

/**
 * Fixed-height card with title bar and internally-scrollable body.
 *
 * Use inside a flex container with `min-h-0` so the card actually fits
 * the viewport instead of growing to its content.
 */
export function Card({
  title,
  meta,
  actions,
  children,
  className = "",
}: {
  title: string;
  meta?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`flex flex-col min-h-0 h-full border border-border-default bg-bg-panel ${className}`}
    >
      <header className="flex items-baseline justify-between gap-3 px-4 py-[10px] border-b border-border-subtle bg-bg-panel shrink-0">
        <h2 className="text-[11px] text-fg-muted tracking-[0.18em] font-medium uppercase font-mono">
          {title}
        </h2>
        <div className="flex items-baseline gap-3">
          {meta && (
            <span className="font-mono text-[10px] text-fg-faint">{meta}</span>
          )}
          {actions}
        </div>
      </header>
      <div className="flex-1 min-h-0 overflow-y-auto">{children}</div>
    </section>
  );
}

/** Tabs strip — client-side state, fits inside a Card's body. */
export function Tabs({
  tabs,
  initial,
  className = "",
}: {
  tabs: Array<{ id: string; label: string; count?: number; panel: ReactNode }>;
  initial?: string;
  className?: string;
}) {
  const [active, setActive] = useState(initial ?? tabs[0]?.id);
  const activeTab = tabs.find((t) => t.id === active) ?? tabs[0];
  return (
    <div className={`flex flex-col h-full min-h-0 ${className}`}>
      <nav
        role="tablist"
        className="flex border-b border-border-subtle bg-bg-panel shrink-0"
      >
        {tabs.map((t) => {
          const isActive = t.id === activeTab?.id;
          return (
            <button
              key={t.id}
              role="tab"
              aria-selected={isActive}
              onClick={() => setActive(t.id)}
              className={`px-4 py-[9px] font-mono text-[10px] uppercase tracking-[0.18em] transition-colors border-b-[2px] -mb-[1px] ${
                isActive
                  ? "text-fg-default bg-bg-base border-b-info-fg"
                  : "text-fg-faint hover:text-fg-default hover:bg-bg-hover border-b-transparent"
              }`}
            >
              {t.label}
              {typeof t.count === "number" && (
                <span className="ml-2 text-fg-faint tabular-nums">
                  {t.count}
                </span>
              )}
            </button>
          );
        })}
      </nav>
      <div className="flex-1 min-h-0 overflow-y-auto">
        {activeTab?.panel}
      </div>
    </div>
  );
}

/** Inset block inside a panel/card — soft separator, no border. */
export function Block({
  label,
  children,
  className = "",
}: {
  label?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`px-4 py-3 border-b border-border-subtle last:border-b-0 ${className}`}>
      {label && (
        <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-fg-faint mb-2">
          {label}
        </div>
      )}
      {children}
    </div>
  );
}

/** Single field row inside a Block. */
export function Row({
  label,
  value,
  mono,
}: {
  label: string;
  value: ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="grid grid-cols-[140px_1fr] gap-3 py-1 items-baseline">
      <dt className="text-fg-faint uppercase tracking-[0.14em] font-mono text-[10px]">
        {label}
      </dt>
      <dd className={`text-fg-muted text-[12px] ${mono ? "font-mono" : ""}`}>
        {value}
      </dd>
    </div>
  );
}

/** Concise page header — short title + one-sentence brief. No multi-paragraph intros. */
export function PageHeader({
  eyebrow,
  title,
  brief,
  actions,
}: {
  eyebrow: string;
  title: string;
  brief?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="border-b border-border-subtle bg-bg-panel shrink-0">
      <div className="px-6 py-3 flex items-start justify-between gap-6">
        <div className="min-w-0">
          <div className="font-mono text-[9px] tracking-[0.22em] text-fg-faint uppercase">
            {eyebrow}
          </div>
          <h1 className="mt-[3px] text-[20px] text-fg-default tracking-tight font-medium leading-tight">
            {title}
          </h1>
          {brief && (
            <p className="mt-[6px] text-[12px] text-fg-muted leading-[1.5] max-w-[640px]">
              {brief}
            </p>
          )}
        </div>
        {actions && <div className="shrink-0">{actions}</div>}
      </div>
    </header>
  );
}
