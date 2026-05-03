import { redirect } from "next/navigation";

/**
 * Audit was merged into the Mission Board (every mission row already carries
 * the operator/status/dispatchedAt/dryRun fields that the audit table
 * surfaced). Old links redirect to the unified surface.
 */
export default function AuditRedirect() {
  redirect("/");
}
