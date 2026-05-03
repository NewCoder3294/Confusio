import { IntelInbox } from "@/components/intel-inbox";

export const metadata = {
  title: "Mendacity — Intel Inbox",
};

export default function IntelInboxPage() {
  return (
    <div className="flex-1 flex flex-col">
      <section className="border-b border-border-subtle bg-bg-panel">
        <div className="max-w-[1400px] mx-auto px-6 py-5">
          <div className="font-mono text-[10px] tracking-[0.18em] text-classified uppercase">
            Defensive — Counter-Synthetic Triage
          </div>
          <h1 className="mt-1 text-2xl text-fg-default tracking-wide font-medium">
            Intel Inbox
          </h1>
          <p className="mt-2 text-[13px] text-fg-muted leading-6 max-w-[820px]">
            Suspect inbound imagery is graded by the same provenance instruments
            the offensive arm uses to grade its own output, plus a spectral
            surrogate classifier and EXIF anomaly checks. Same instruments,
            inverted operationally. A high-confidence synthetic verdict here
            means the artifact would not survive scrutiny by an analyst running
            this stack in reverse.
          </p>
        </div>
      </section>

      <div className="max-w-[1400px] w-full mx-auto px-6 py-6 flex-1">
        <IntelInbox />
      </div>
    </div>
  );
}
