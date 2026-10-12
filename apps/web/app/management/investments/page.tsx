import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import InvestmentForm from "@/components/InvestmentForm";
import InvestmentRegister from "@/components/InvestmentRegister";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { investmentFilters, investmentsUrl, type InvestmentPage } from "@/lib/investments";
import { MANAGEMENT_HOME, MANAGEMENT_ROLE_LABEL, managementNavFor, type ManagementMe } from "@/lib/management";

const UNAVAILABLE = "Investments are unavailable right now. Please try again.";

// mgmt-014 (EVID-017 §23, MI13): the investment register, partner-only (M13). The API refuses everyone else, the accountant and the super
// admin included, and that refusal is shown as the access card; a 422 (bad filters) is shown above the form, which keeps them.
export default async function ManagementInvestmentsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const filters = investmentFilters(await searchParams);
  let me: ManagementMe;
  try {
    me = await serverApi<ManagementMe>("/api/v1/management/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  let data: InvestmentPage | null = null;
  let error = "";
  try {
    data = await serverApi<InvestmentPage>(investmentsUrl(filters));
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return accessUnavailable(e, "/admin/login");
    error = e instanceof ApiError && e.status === 422 ? e.message : UNAVAILABLE;
  }
  return (
    <PortalShell nav={managementNavFor(me.tiers)} roleLabel={MANAGEMENT_ROLE_LABEL[me.role] ?? me.role} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow"><Link href={MANAGEMENT_HOME}>Command Center</Link></div>
            <h2>Investments &amp; ROI</h2>
            <p className="muted">Where company money is invested and what it produces. Partners only. Amounts are in rupees; ROI = (actual return − amount) ÷ amount.</p>
          </div>
        </div>
        <InvestmentForm investors={data?.investors ?? []} />
        <InvestmentRegister data={data} error={error} filters={filters} />
      </div>
    </PortalShell>
  );
}
