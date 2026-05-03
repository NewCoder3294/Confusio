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
  children,
  className = "",
}: {
  title: string;
  meta?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`flex flex-col border border-border-default bg-bg-panel max-h-[calc(100vh-180px)] ${className}`}
    >
      <header className="flex items-baseline justify-between px-4 py-2 border-b border-border-default bg-bg-elevated shrink-0">
        <h2 className="text-[14px] text-fg-default tracking-wide font-medium uppercase">
          {title}
        </h2>
        {meta && (
          <span className="font-mono text-[10px] text-fg-faint">{meta}</span>
        )}
      </header>
      <div className="min-h-0 overflow-y-auto">{children}</div>
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
        className="flex border-b border-border-subtle bg-bg-base shrink-0"
      >
        {tabs.map((t) => {
          const isActive = t.id === activeTab?.id;
          return (
            <button
              key={t.id}
              role="tab"
              aria-selected={isActive}
              onClick={() => setActive(t.id)}
              className={`px-4 py-2 font-mono text-[11px] uppercase tracking-[0.16em] border-r border-border-subtle transition-colors ${
                isActive
                  ? "text-fg-default bg-bg-panel border-b-[2px] border-b-info-fg -mb-[1px]"
                  : "text-fg-faint hover:text-fg-default hover:bg-bg-hover"
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
      <div className="px-6 py-3 flex items-baseline justify-between gap-6">
        <div>
          <div className="font-mono text-[10px] tracking-[0.18em] text-classified uppercase">
            {eyebrow}
          </div>
          <h1 className="mt-[2px] text-xl text-fg-default tracking-wide font-medium">
            {title}
          </h1>
          {brief && (
            <p className="mt-1 text-[12px] text-fg-muted leading-5 max-w-[680px]">
              {brief}
            </p>
          )}
        </div>
        {actions && <div className="shrink-0">{actions}</div>}
      </div>
    </header>
  );
}
