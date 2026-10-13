import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import ManagementItRevenue from "@/components/ManagementItRevenue";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { MANAGEMENT_HOME, MANAGEMENT_ROLE_LABEL, managementNavFor, type ManagementMe } from "@/lib/management";
import { istMonth } from "@/lib/managementExpenses";
import { itRevenuePaymentsUrl, itRevenueQuery, itRevenueUrl, type ItRevenue, type ItRevenuePaymentPage } from "@/lib/managementItRevenue";

const UNAVAILABLE = "IT Training revenue is unavailable right now. Please try again.";
const PAYMENTS_UNAVAILABLE = "The payments are unavailable right now. Please try again.";

function message(e: unknown, fallback: string): string {
  return e instanceof ApiError && e.status === 422 && typeof e.message === "string" && !e.message.startsWith("[object") ? e.message : fallback;
}

// mgmt-007 (EVID-017 §5, spec IR1-IR12): IT Training revenue for the finance tier. The API refuses everyone else (the super admin
// included, M13), shown as the access card. The dashboard and the chosen payment list load together; either can fail on its own.
export default async function ManagementItRevenuePage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const query = itRevenueQuery(await searchParams);
  let me: ManagementMe;
  try {
    me = await serverApi<ManagementMe>("/api/v1/management/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  const [figures, list] = await Promise.allSettled([
    serverApi<ItRevenue>(itRevenueUrl(query)),
    query.scope ? serverApi<ItRevenuePaymentPage>(itRevenuePaymentsUrl(query)) : Promise.resolve(null),
  ]);
  if (figures.status === "rejected" && figures.reason instanceof ApiError && (figures.reason.status === 401 || figures.reason.status === 403)) {
    return accessUnavailable(figures.reason, "/admin/login");
  }
  return (
    <PortalShell nav={managementNavFor(me.tiers)} roleLabel={MANAGEMENT_ROLE_LABEL[me.role] ?? me.role} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">
              <Link href={MANAGEMENT_HOME}>Command Center</Link>
            </div>
            <h2>IT Training revenue</h2>
          </div>
        </div>
        <ManagementItRevenue
          data={figures.status === "fulfilled" ? figures.value : null}
          error={figures.status === "rejected" ? message(figures.reason, UNAVAILABLE) : ""}
          query={query}
          maxMonth={istMonth()}
          payments={list.status === "fulfilled" ? list.value : null}
          paymentsError={list.status === "rejected" ? message(list.reason, PAYMENTS_UNAVAILABLE) : ""}
        />
      </div>
    </PortalShell>
  );
}
