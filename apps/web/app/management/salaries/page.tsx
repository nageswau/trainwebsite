import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import Departments from "@/components/Departments";
import PortalShell from "@/components/PortalShell";
import SalaryGrid from "@/components/SalaryGrid";
import { ApiError, serverApi } from "@/lib/api";
import { MANAGEMENT_HOME, MANAGEMENT_ROLE_LABEL, managementNavFor, type ManagementMe } from "@/lib/management";
import { DEPARTMENTS_API, SALARIES_HOME, salariesUrl, salaryMonth, type Department, type SalaryMonth } from "@/lib/salaries";

const UNAVAILABLE = "Salaries are unavailable right now. Please try again.";
const FUTURE = "Salaries can be recorded up to the current month. Pick another month."; // the only 422 left: a malformed month is dropped

// mgmt-011 (EVID-017 §9, spec SM13): salary totals per department for a month, the employee cost and the Employee Cost Ratio. Finance
// tier only (M13): the API refuses super_admin and everyone else, and that refusal is shown as the access card. A 422 (a future month)
// is shown above the month form, which stays so another month can be picked.
export default async function ManagementSalariesPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const month = salaryMonth(await searchParams);
  let me: ManagementMe;
  try {
    me = await serverApi<ManagementMe>("/api/v1/management/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  let data: SalaryMonth | null = null;
  let departments: Department[] = [];
  let error = "";
  try {
    [data, departments] = await Promise.all([
      serverApi<SalaryMonth>(salariesUrl(month)),
      serverApi<{ items: Department[] }>(DEPARTMENTS_API).then((page) => page.items),
    ]);
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
            <h2>Salaries &amp; employee cost</h2>
            <p className="muted">Monthly salary totals per department (no individual salaries). Partners and the accountant only. Amounts are in rupees.</p>
          </div>
        </div>
        <form method="get" action={SALARIES_HOME} aria-label="Choose a month" className="analytics-form action-card" key={month} autoComplete="off">
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor="salaries-month">Month</label>
            <input id="salaries-month" className="input" type="month" name="month" defaultValue={data?.month ?? month} max={data?.current_month} required />
          </div>
          <button className="btn secondary" type="submit">Show month</button>
        </form>
        {error && <p className="form-error" role="alert">{error}</p>}
        {data && <SalaryGrid key={data.month} data={data} />}
        {data && <Departments departments={departments} />}
      </div>
    </PortalShell>
  );
}
