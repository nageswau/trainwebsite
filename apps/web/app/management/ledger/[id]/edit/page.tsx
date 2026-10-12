import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import LedgerEntryForm from "@/components/LedgerEntryForm";
import LedgerShell from "@/components/LedgerShell";
import { ApiError, serverApi } from "@/lib/api";
import { indiaToday } from "@/lib/bdmTravel";
import type { ManagementMe } from "@/lib/management";
import { LEDGER_API, LEDGER_HOME, type LedgerEntryDetail, type LedgerOptions } from "@/lib/managementLedger";

// mgmt-004 (ML7, ML12): change a draft or rejected entry. Any other status is locked; the page says so instead of showing the form.
export default async function EditLedgerEntryPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let me: ManagementMe;
  let entry: LedgerEntryDetail | null = null;
  let options: LedgerOptions | null = null;
  try {
    me = await serverApi<ManagementMe>("/api/v1/management/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  try {
    [entry, options] = await Promise.all([serverApi<LedgerEntryDetail>(`${LEDGER_API}/${encodeURIComponent(id)}`), serverApi<LedgerOptions>(`${LEDGER_API}/options`)]);
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return accessUnavailable(e, "/admin/login");
    if (!(e instanceof ApiError && (e.status === 404 || e.status === 422))) throw e;
  }
  if (!entry || !options) {
    return (
      <LedgerShell me={me} title="Ledger entry not found">
        <p className="empty" role="status">This entry does not exist. <Link className="kpi-link" href={LEDGER_HOME}>Back to the ledger</Link></p>
      </LedgerShell>
    );
  }
  return (
    <LedgerShell me={me} title="Edit ledger entry" intro={entry.status === "rejected" ? "Saving a change returns this rejected entry to draft." : undefined}>
      {entry.can.edit ? (
        <LedgerEntryForm options={options} today={indiaToday()} entry={entry} />
      ) : (
        <p className="empty" role="status">This entry can no longer be changed. <Link className="kpi-link" href={`${LEDGER_HOME}/${entry.id}`}>Back to the entry</Link></p>
      )}
    </LedgerShell>
  );
}
