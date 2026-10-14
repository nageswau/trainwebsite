import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import CapitalEntryForm from "@/components/CapitalEntryForm";
import CapitalSharesForm from "@/components/CapitalSharesForm";
import PartnerCapital from "@/components/PartnerCapital";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { MANAGEMENT_HOME, MANAGEMENT_ROLE_LABEL, managementNavFor, type ManagementMe } from "@/lib/management";
import { capitalQuery, capitalUrl, type Capital } from "@/lib/partnerCapital";

const UNAVAILABLE = "Capital accounts are unavailable right now. Please try again.";

// mgmt-015 (EVID-017 §24, spec CP1-CP15): the partners' capital accounts, partner-only (M13). The API refuses everyone else, the
// accountant and the super admin included, and that refusal is shown as the access card; a 422 (a month out of range) keeps the form.
export default async function PartnerCapitalPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const query = capitalQuery(await searchParams);
  let me: ManagementMe;
  try {
    me = await serverApi<ManagementMe>("/api/v1/management/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  let data: Capital | null = null;
  let error = "";
  try {
    data = await serverApi<Capital>(capitalUrl(query));
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return accessUnavailable(e, "/admin/login");
    error = e instanceof ApiError && e.status === 422 && typeof e.message === "string" && !e.message.startsWith("[object") ? e.message : UNAVAILABLE;
  }
  return (
    <PortalShell nav={managementNavFor(me.tiers)} roleLabel={MANAGEMENT_ROLE_LABEL[me.role] ?? me.role} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow"><Link href={MANAGEMENT_HOME}>Command Center</Link></div>
            <h2>Partner capital accounts</h2>
            <p className="muted">Each partner&apos;s capital, share % and indicative profit share. Partners only. Amounts are in rupees.</p>
          </div>
        </div>
        {data && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "flex-start" }}>
            <CapitalEntryForm partners={data.partners} accounts={data.accounts} today={data.as_of} />
            <CapitalSharesForm partners={data.partners} accounts={data.accounts} month={data.as_of.slice(0, 7)} />
          </div>
        )}
        <PartnerCapital data={data} error={error} query={query} />
      </div>
    </PortalShell>
  );
}
