import Link from "next/link";
import { redirect } from "next/navigation";

import { accessUnavailable } from "@/components/AccessUnavailable";
import ManagementTelecalling from "@/components/ManagementTelecalling";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { MANAGEMENT_HOME, MANAGEMENT_ROLE_LABEL, managementNavFor, type ManagementMe } from "@/lib/management";
import { telecallingFilters, telecallingHref, telecallingUrl, type Telecalling } from "@/lib/managementTelecalling";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

const UNAVAILABLE = "The telecalling dashboard is unavailable right now. Please try again.";

// mgmt-019 (EVID-017 §14, spec TC15): the company-wide Telecalling dashboard for the operational tier (partner, super_admin). The API
// refuses everyone else (the accountant's 403 included), shown as the access card. A 422 (the period rules) shows the API's words.
export default async function ManagementTelecallingPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const search = await searchParams;
  const filters = telecallingFilters(search);
  // The GET form sends both dates; one redirect drops an empty one so the address is short and shareable.
  if (Object.values(search).some((value) => value === "")) redirect(telecallingHref(filters));
  let me: ManagementMe;
  try {
    me = await serverApi<ManagementMe>("/api/v1/management/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  let data: Telecalling | null = null;
  let error = "";
  try {
    data = await serverApi<Telecalling>(telecallingUrl(filters));
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return accessUnavailable(e, "/admin/login");
    error = e instanceof ApiError && e.status === 422 ? e.message : UNAVAILABLE;
  }
  return (
    <PortalShell nav={me.role === "super_admin" ? SUPER_ADMIN_NAV : managementNavFor(me.tiers)} roleLabel={MANAGEMENT_ROLE_LABEL[me.role] ?? me.role} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">
              <Link href={MANAGEMENT_HOME}>Command Center</Link>
            </div>
            <h2>Telecalling</h2>
          </div>
        </div>
        <ManagementTelecalling data={data} error={error} filters={filters} />
      </div>
    </PortalShell>
  );
}
