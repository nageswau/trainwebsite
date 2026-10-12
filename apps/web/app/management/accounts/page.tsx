import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import AccountsDashboard from "@/components/AccountsDashboard";
import BalancesForm from "@/components/BalancesForm";
import PortalShell from "@/components/PortalShell";
import { ACCOUNTS_HOME, accountsUrl, type AccountsMonth } from "@/lib/accounts";
import { ApiError, serverApi } from "@/lib/api";
import { MANAGEMENT_HOME, MANAGEMENT_ROLE_LABEL, managementNavFor, type ManagementMe } from "@/lib/management";
import { salaryMonth } from "@/lib/salaries";

const UNAVAILABLE = "Accounts are unavailable right now. Please try again.";
const FUTURE = "Accounts can be shown up to the current month. Pick another month."; // the only 422 left: a malformed month is dropped

// mgmt-013 (EVID-017 §22, spec AD13): the month's income and expense heads, the financial position and the month-end balances form.
// Finance tier only (M13): the API refuses super_admin and everyone else, and that refusal is shown as the access card. A 422 (a future
// month) is shown above the month form, which stays so another month can be picked.
export default async function ManagementAccountsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const month = salaryMonth(await searchParams);
  let me: ManagementMe;
  try {
    me = await serverApi<ManagementMe>("/api/v1/management/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  let data: AccountsMonth | null = null;
  let error = "";
  try {
    data = await serverApi<AccountsMonth>(accountsUrl(month));
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return accessUnavailable(e, "/admin/login");
    error = e instanceof ApiError && e.status === 422 ? FUTURE : UNAVAILABLE;
  }
  return (
    <PortalShell nav={managementNavFor(me.tiers)} roleLabel={MANAGEMENT_ROLE_LABEL[me.role] ?? me.role} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow"><Link href={MANAGEMENT_HOME}>Command Center</Link></div>
            <h2>Accounts</h2>
            <p className="muted">Income, expenses and the financial position, connected to the ledger and the modules that bill. Partners and the accountant only. Amounts are in rupees.</p>
          </div>
        </div>
        <form method="get" action={ACCOUNTS_HOME} aria-label="Choose a month" className="analytics-form action-card" key={month} autoComplete="off">
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor="accounts-month">Month</label>
            <input id="accounts-month" className="input" type="month" name="month" defaultValue={data?.month ?? month} max={data?.current_month} required />
          </div>
          <button className="btn secondary" type="submit">Show month</button>
        </form>
        {error && <p className="form-error" role="alert">{error}</p>}
        {data && <AccountsDashboard data={data} />}
        {data && <BalancesForm key={data.month} data={data} />}
      </div>
    </PortalShell>
  );
}
