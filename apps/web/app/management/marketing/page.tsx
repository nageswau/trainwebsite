import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import MarketingBudgetForm from "@/components/MarketingBudgetForm";
import MarketingDashboard from "@/components/MarketingDashboard";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { MANAGEMENT_HOME, MANAGEMENT_ROLE_LABEL, managementNavFor, type ManagementMe } from "@/lib/management";
import { MARKETING_HOME, marketingUrl, type MarketingMonth } from "@/lib/marketing";
import { salaryMonth } from "@/lib/salaries";

const UNAVAILABLE = "Marketing figures are unavailable right now. Please try again.";
const FUTURE = "Marketing can be shown up to the current month. Pick another month."; // the only 422 left: a malformed month is dropped

// mgmt-012 (EVID-017 §10, §15, spec MK14): the month's marketing figures, ROI per channel, campaigns and (finance tier) the budget form.
// Every management role reads it; the API sends money to partners and the accountant only (MK11), and refuses everyone else, which is
// shown as the access card. A 422 (a future month) is shown above the month form, which stays so another month can be picked.
export default async function ManagementMarketingPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const month = salaryMonth(await searchParams);
  let me: ManagementMe;
  try {
    me = await serverApi<ManagementMe>("/api/v1/management/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  let data: MarketingMonth | null = null;
  let error = "";
  try {
    data = await serverApi<MarketingMonth>(marketingUrl(month));
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
            <h2>Marketing budget &amp; ROI</h2>
            <p className="muted">What each lead source costs and brings: budget, spend, leads, conversions, revenue and ROI. What is working, what should stop, where to invest more.</p>
          </div>
        </div>
        <form method="get" action={MARKETING_HOME} aria-label="Choose a month" className="analytics-form action-card" key={month} autoComplete="off">
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor="marketing-month">Month</label>
            <input id="marketing-month" className="input" type="month" name="month" defaultValue={data?.month ?? month} max={data?.current_month} required />
          </div>
          <button className="btn secondary" type="submit">Show month</button>
        </form>
        {error && <p className="form-error" role="alert">{error}</p>}
        {data && <MarketingDashboard data={data} />}
        {data?.money_visible && <MarketingBudgetForm key={data.month} data={data} />}
      </div>
    </PortalShell>
  );
}
