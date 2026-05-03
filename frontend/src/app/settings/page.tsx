import {
  readSettings,
  ENV_FILE_PATH_FOR_DISPLAY,
} from "@/lib/settings";
import { PageHeader } from "@/components/surfaces";
import { SettingsForm } from "@/components/settings-form";

export const metadata = {
  title: "Mendacity — Settings",
};

export default async function SettingsPage() {
  const snap = await readSettings();
  return (
    <>
      <PageHeader
        eyebrow="Operator settings"
        title="Credentials & providers"
        brief="API keys for the providers Mendacity talks to. Stored in social/config/api_credentials.env on this host. Never echoed back — fields show masked previews and clear on focus."
      />
      <div className="flex-1 min-h-0 w-full mx-auto px-6 py-3 overflow-y-auto">
        <div className="max-w-[860px]">
          <SettingsForm initial={snap} envPath={ENV_FILE_PATH_FOR_DISPLAY} />
        </div>
      </div>
    </>
  );
}
