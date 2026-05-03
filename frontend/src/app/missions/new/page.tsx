import { listChannels } from "@/lib/foundry";
import { NewMissionForm } from "@/components/new-mission-form";

export const metadata = {
  title: "Mendacity — New Mission",
};

export default async function NewMissionPage() {
  const channels = await listChannels();
  const sandboxChannels = channels
    .filter((c) => c.isSandbox)
    .sort((a, b) => a.displayName.localeCompare(b.displayName));

  return (
    <div className="flex-1 flex flex-col">
      <section className="border-b border-border-subtle bg-bg-panel">
        <div className="max-w-[1400px] mx-auto px-6 py-5">
          <div className="font-mono text-[10px] tracking-[0.18em] text-classified uppercase">
            Mission Dispatch — Operator Intent → Spec → Inbox
          </div>
          <h1 className="mt-1 text-2xl text-fg-default tracking-wide font-medium">
            New Mission
          </h1>
          <p className="mt-2 text-[13px] text-fg-muted leading-6 max-w-[820px]">
            The console emits a strict <span className="font-mono">MissionSpec</span>{" "}
            (PALANTIR_BRIEF.md §4.1) atomically into{" "}
            <span className="font-mono">missions/inbox/</span>. The local
            engine watches the dir, runs persona generation, image generation,
            provenance grading, and watermark stripping, and writes a result
            JSON the bridge ingests back into the Foundry Ontology. Status
            propagates to the Mission Board within seconds.
          </p>
        </div>
      </section>

      <div className="max-w-[820px] w-full mx-auto px-6 py-8">
        <NewMissionForm
          sandboxChannels={sandboxChannels.map((c) => ({
            id: c.channel_id,
            displayName: c.displayName,
            audienceProfile: c.audienceProfile,
          }))}
        />
      </div>
    </div>
  );
}
