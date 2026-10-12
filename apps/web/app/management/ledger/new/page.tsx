import { accessUnavailable } from "@/components/AccessUnavailable";
import LedgerEntryForm from "@/components/LedgerEntryForm";
import LedgerShell from "@/components/LedgerShell";
import { ApiError, serverApi } from "@/lib/api";
import { indiaToday } from "@/lib/bdmTravel";
import type { ManagementMe } from "@/lib/management";
import { LEDGER_API, type LedgerOptions } from "@/lib/managementLedger";

// mgmt-004 (ML4-ML8): a new ledger entry. The form's choices come from the API (active categories, channels, courses and batches);
// the API refuses anyone outside the finance tier.
export default async function NewLedgerEntryPage() {
  let me: ManagementMe;
  let options: LedgerOptions;
  try {
    me = await serverApi<ManagementMe>("/api/v1/management/me");
    options = await serverApi<LedgerOptions>(`${LEDGER_API}/options`);
  } catch (e) {
    if (e instanceof ApiError && e.status >= 500) throw e;
    return accessUnavailable(e, "/admin/login");
  }
  return (
    <LedgerShell me={me} title="New ledger entry" intro="Saved entries start as drafts. Submit one when it is ready; it counts in the figures once a partner approves it.">
      <LedgerEntryForm options={options} today={indiaToday()} />
    </LedgerShell>
  );
}
