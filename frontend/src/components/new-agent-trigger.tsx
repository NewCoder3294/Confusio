"use client";

import { useState } from "react";
import { NewAgentModal } from "./new-agent-modal";

type AgentLite = {
  id: string;
  name: string;
  language: string;
  geoAnchor: string;
};

export function NewAgentTrigger({ agents }: { agents: AgentLite[] }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="border border-info-border bg-info-bg hover:opacity-90 px-4 py-2 font-mono text-[11px] uppercase tracking-[0.16em] text-info-fg"
      >
        + New agent
      </button>
      <NewAgentModal
        agents={agents}
        open={open}
        onClose={() => setOpen(false)}
      />
    </>
  );
}
