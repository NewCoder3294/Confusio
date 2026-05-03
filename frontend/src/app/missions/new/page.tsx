import { listChannels } from "@/lib/foundry";
import { NewMissionForm } from "@/components/new-mission-form";
import { PageHeader } from "@/components/surfaces";

export const metadata = {
  title: "Mendacity — New Mission",
};

export default async function NewMissionPage() {
  const channels = await listChannels();
  const sandboxChannels = channels
    .filter((c) => c.isSandbox)
    .sort((a, b) => a.displayName.localeCompare(b.displayName));

  return (
    <>
      <PageHeader
        eyebrow="Mission dispatch — Operator intent → spec → inbox"
        title="New Mission"
        brief="The console emits a MissionSpec atomically into missions/inbox/. The engine picks it up, runs persona + image generation + provenance grading, and writes the result back."
      />
      <div className="flex-1 min-h-0 overflow-y-auto">
        <div className="max-w-[820px] w-full mx-auto px-6 py-6">
          <NewMissionForm
            sandboxChannels={sandboxChannels.map((c) => ({
              id: c.channel_id,
              displayName: c.displayName,
              audienceProfile: c.audienceProfile,
            }))}
          />
        </div>
      </div>
    </>
  );
}
