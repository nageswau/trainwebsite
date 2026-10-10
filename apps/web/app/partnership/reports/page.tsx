import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PartnershipReportView from "@/components/PartnershipReportView";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { type PartnershipReport, REPORT_READERS, SUMMARIES, reportKind, reportParams, reportUrl } from "@/lib/partnershipReports";
import type { User } from "@/lib/types";
import { shellFor } from "@/lib/universities";

const UNAVAILABLE = "This report is unavailable right now. Please try again.";

// upc-031 (DEC-SCOPE-171, §32 "Reports"): the five partnership reports. The API decides the scope (a manager's universities, a head's team
// + unowned, everything for super_admin) and every figure; the role check here only spares other roles a screen that can only fail. A 422
// (a refused filter) is shown above the form; a 403 is the access card.
export default async function PartnershipReportsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const search = await searchParams;
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/overseas/login");
  }
  if (!REPORT_READERS.has(user.role)) return accessDenied(user, "Partnership reports access required");
  const kind = reportKind(typeof search.report === "string" ? search.report : undefined);
  const params = reportParams(search);
  let report: PartnershipReport | null = null;
  let error = "";
  try {
    report = await serverApi<PartnershipReport>(reportUrl(kind, params));
  } catch (e) {
    if (e instanceof ApiError && e.status === 403) return accessUnavailable(e, "/overseas/login");
    error = e instanceof ApiError && e.status === 422 ? e.message : UNAVAILABLE;
  }
  const { nav, roleLabel } = shellFor(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">University Partnerships</div>
            <h2>Reports</h2>
            <p className="muted">{SUMMARIES[kind]} Download any report as CSV.</p>
          </div>
        </div>
        <PartnershipReportView kind={kind} report={report} error={error} params={params} />
      </div>
    </PortalShell>
  );
}
