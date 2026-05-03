import { listChannels, type Channel } from "@/lib/foundry";
import { NewChannelForm } from "@/components/channel-admin";
import { PageHeader } from "@/components/surfaces";

export const metadata = {
  title: "Mendacity — Channels",
};

export default async function ChannelsPage() {
  const channels = await listChannels();
  const sandbox = channels.filter((c) => c.isSandbox);
  const nonSandbox = channels.filter((c) => !c.isSandbox);

  return (
    <>
      <PageHeader
        eyebrow="Allowlist administration"
        title="Channels"
        brief="Delivery targets. Missions resolve their channel through this list before the engine accepts them. Sandbox-only from this surface."
      />
      <div className="flex-1 min-h-0 overflow-y-auto">
        <div className="w-full mx-auto px-6 py-4 grid grid-cols-[1fr_360px] gap-4">
          <div className="flex flex-col gap-4">
            <ChannelTable
              title="Sandbox channels"
              subtitle={`${sandbox.length} active`}
              channels={sandbox}
              tone="pass"
            />
            {nonSandbox.length > 0 && (
              <ChannelTable
                title="Non-sandbox"
                subtitle="Read-only · J2 + OGC sign-off required"
                channels={nonSandbox}
                tone="fail"
              />
            )}
          </div>
          <aside className="flex flex-col gap-3">
            <NewChannelForm />
            <Reference />
          </aside>
        </div>
      </div>
    </>
  );
}

function ChannelTable({
  title,
  subtitle,
  channels,
  tone,
}: {
  title: string;
  subtitle: string;
  channels: Channel[];
  tone: "pass" | "fail";
}) {
  const PILL: Record<typeof tone, string> = {
    pass: "border-pass-border bg-pass-bg text-pass-fg",
    fail: "border-fail-border bg-fail-bg text-fail-fg",
  };
  return (
    <section>
      <div className="flex items-baseline justify-between mb-2">
        <h2 className="text-[11px] font-mono uppercase tracking-[0.18em] text-fg-faint">
          {title}
        </h2>
        <span className="text-[10px] font-mono text-fg-faint italic">
          {subtitle}
        </span>
      </div>
      <div className="border border-border-subtle bg-bg-panel">
        {channels.length === 0 ? (
          <div className="px-4 py-6 text-fg-faint italic text-[12px] text-center">
            No channels in this category.
          </div>
        ) : (
          <table className="w-full text-[12px]">
            <thead>
              <tr className="border-b border-border-subtle text-[10px] uppercase tracking-[0.14em] text-fg-faint font-mono">
                <th className="text-left px-3 py-2 font-medium">Channel ID</th>
                <th className="text-left px-3 py-2 font-medium">Display name</th>
                <th className="text-left px-3 py-2 font-medium">Platform</th>
                <th className="text-left px-3 py-2 font-medium">Audience</th>
                <th className="text-left px-3 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {channels.map((c) => (
                <tr
                  key={c.channel_id}
                  className="border-b border-border-subtle last:border-b-0 hover:bg-bg-hover"
                >
                  <td className="px-3 py-2 font-mono text-fg-mono">
                    {c.channel_id}
                  </td>
                  <td className="px-3 py-2 text-fg-default">{c.displayName}</td>
                  <td className="px-3 py-2 font-mono text-[11px] text-fg-muted uppercase tracking-[0.14em]">
                    {c.platform}
                  </td>
                  <td className="px-3 py-2 text-fg-muted italic">
                    {c.audienceProfile || "—"}
                  </td>
                  <td className="px-3 py-2">
                    <span
                      className={`inline-block border font-mono font-medium uppercase px-2 py-[2px] text-[10px] tracking-[0.14em] ${PILL[tone]}`}
                    >
                      {tone === "pass" ? "SANDBOX" : "RESTRICTED"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}

function Reference() {
  return (
    <div className="border border-border-subtle bg-bg-panel">
      <header className="px-4 py-2 border-b border-border-subtle">
        <h2 className="text-[11px] font-mono uppercase tracking-[0.18em] text-fg-faint">
          Reference
        </h2>
      </header>
      <ul className="px-4 py-3 flex flex-col gap-2 text-[11px] text-fg-muted leading-5">
        <li>
          <span className="font-mono text-fg-default">channel_id</span> is the
          PK; immutable once created.
        </li>
        <li>
          Foundry actions used:{" "}
          <span className="font-mono text-fg-default">create-channel</span>,{" "}
          <span className="font-mono text-fg-default">edit-channel</span>,{" "}
          <span className="font-mono text-fg-default">delete-channel</span>.
        </li>
        <li>
          The MissionPlanner agent refuses any channel where{" "}
          <span className="font-mono text-fg-default">isSandbox=false</span>.
        </li>
      </ul>
    </div>
  );
}
