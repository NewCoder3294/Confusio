"use client";

import { useState } from "react";
import { NewMissionModal } from "./new-mission-modal";

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

export function DispatchButton({
  channels,
  personas,
}: {
  channels: Channel[];
  personas: PersonaLite[];
}) {
  const [open, setOpen] = useState(false);
  const disabled = channels.length === 0 || personas.length === 0;
  return (
    <>
      <button
        onClick={() => setOpen(true)}
        disabled={disabled}
        title={
          disabled
            ? "Need at least one sandbox channel and one persona to dispatch."
            : "Walk through a new mission dispatch."
        }
        className="flex flex-col justify-center px-4 border border-info-border bg-info-bg/40 hover:bg-info-bg text-info-fg transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
      >
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] opacity-80">
          Dispatch
        </span>
        <span className="font-mono text-[12px] tracking-wide">
          + New mission
        </span>
      </button>
      <NewMissionModal
        channels={channels}
        personas={personas}
        open={open}
        onClose={() => setOpen(false)}
      />
    </>
  );
}
