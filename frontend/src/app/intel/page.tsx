import { IntelInbox } from "@/components/intel-inbox";
import { PageHeader } from "@/components/surfaces";

export const metadata = {
  title: "Mendacity — Intel Inbox",
};

export default function IntelInboxPage() {
  return (
    <>
      <PageHeader
        eyebrow="Defensive — Counter-synthetic triage"
        title="Intel Inbox"
        brief="Same instruments the offensive arm uses to grade itself, pointed at suspect inbound imagery. C2PA + spectral surrogate + EXIF anomalies → composite verdict."
      />
      <div className="flex-1 min-h-0 w-full mx-auto px-6 py-3">
        <IntelInbox />
      </div>
    </>
  );
}
