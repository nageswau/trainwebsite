import Link from "next/link";
import { notFound } from "next/navigation";

import { accessUnavailable } from "@/components/AccessUnavailable";
import ManagementDrillDown from "@/components/ManagementDrillDown";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { MANAGEMENT_HOME, MANAGEMENT_ROLE_LABEL, managementNavFor, type ManagementMe } from "@/lib/management";
import { DRILL_LABEL, drillQuery, drillUrl, isDrillChain, type Drill } from "@/lib/managementDrill";
import { istMonth } from "@/lib/managementExpenses";

const UNAVAILABLE = "The drill-down is unavailable right now. Please try again.";

function message(e: unknown): string {
  return e instanceof ApiError && (e.status === 404 || e.status === 422) && typeof e.message === "string" && !e.message.startsWith("[object") ? e.message : UNAVAILABLE;
}

// mgmt-033 (EVID-017 "the key difference", spec DD1-DD14): a revenue chain, one level at a time, for the finance tier. The API refuses
// everyone else (the super admin included, AC3), shown as the access card; a tampered or stale path gets the API's 404/422 message.
export default async function ManagementDrillPage({
  params, searchParams,
}: { params: Promise<{ chain: string }>; searchParams: Promise<Record<string, string | string[] | undefined>> }) { // prettier-ignore
  const { chain } = await params;
  if (!isDrillChain(chain)) notFound();
  const query = drillQuery(await searchParams);
  let me: ManagementMe;
  try {
    me = await serverApi<ManagementMe>("/api/v1/management/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  let data: Drill | null = null;
  let error = "";
  try {
    data = await serverApi<Drill>(drillUrl(chain, query));
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return accessUnavailable(e, "/admin/login");
    error = message(e);
  }
  return (
    <PortalShell nav={managementNavFor(me.tiers)} roleLabel={MANAGEMENT_ROLE_LABEL[me.role] ?? me.role} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">
              <Link href={MANAGEMENT_HOME}>Command Center</Link>
            </div>
            <h2>{DRILL_LABEL[chain]}: drill-down</h2>
          </div>
        </div>
        <ManagementDrillDown chain={chain} data={data} error={error} query={query} maxMonth={istMonth()} />
      </div>
    </PortalShell>
  );
}
