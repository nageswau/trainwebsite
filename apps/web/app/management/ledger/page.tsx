import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import LedgerShell from "@/components/LedgerShell";
import ManagementLedger from "@/components/ManagementLedger";
import { ApiError, serverApi } from "@/lib/api";
import type { ManagementMe } from "@/lib/management";
import { LEDGER_API, LEDGER_HOME, ledgerFilters, ledgerUrl, type LedgerCategory, type LedgerPage } from "@/lib/managementLedger";

const UNAVAILABLE = "The ledger is unavailable right now. Please try again.";

// mgmt-004 (EVID-017 §8/§22, ML10/ML15/ML16): the ledger list. The API refuses everyone outside the finance tier (the super admin
// included, M13), and the page then shows the access card. A partner gets the approval queue (the list filtered to submitted entries).
export default async function ManagementLedgerPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const filters = ledgerFilters(await searchParams);
  let me: ManagementMe;
  try {
    me = await serverApi<ManagementMe>("/api/v1/management/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  let data: LedgerPage | null = null;
  let categories: LedgerCategory[] = [];
  let error = "";
  try {
    [data, { items: categories }] = await Promise.all([serverApi<LedgerPage>(ledgerUrl(filters)), serverApi<{ items: LedgerCategory[] }>(`${LEDGER_API}/categories`)]);
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return accessUnavailable(e, "/admin/login");
    data = null;
    error = UNAVAILABLE;
  }
  const actions = (
    <>
      <Link className="btn" href={`${LEDGER_HOME}/new`}>New entry</Link>
      {me.role === "partner" && <Link className="btn secondary" href={`${LEDGER_HOME}?status=submitted`}>Awaiting approval</Link>}
      <Link className="btn secondary" href={`${LEDGER_HOME}/categories`}>Categories</Link>
    </>
  );
  return (
    <LedgerShell me={me} title="Ledger" actions={actions} intro="Manual income and expenses, in rupees. The accountant and partners record entries; a partner approves each one before it counts. Approved entries are corrected by a reversal, never edited. Choose “Manual + automatic” to add the money other modules record.">
      <ManagementLedger data={data} error={error} filters={filters} categories={categories} commissionVisible={me.tiers.partner_only} />
    </LedgerShell>
  );
}
