import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PoActivityReport from "@/components/PoActivityReport";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { isUuid } from "@/lib/bdmTravel";
import { companyShell, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import { chosenPeriod, MANAGER_REPORTS_PATH, memberReportUrl, periodLabel, type Report } from "@/lib/recruiterPoWork";
import { istToday } from "@/lib/telecallerTargets";
import type { User } from "@/lib/types";

// pob-009 T7/T8: one team member's report for the Team Lead, read only, with the contacts behind the response rate.
export default async function MemberReportPage({ params, searchParams }: { params: Promise<{ userId: string }>; searchParams: Promise<{ period?: string; start?: string }> }) {
  const { userId } = await params;
  const today = istToday();
  const { period, start } = chosenPeriod(await searchParams, today);
  let user: User;
  let report: Report | null = null;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (user.role !== "placement_manager" && user.role !== "super_admin") return accessDenied(user, "This page is for Team Leads.");
    if (!isUuid(userId)) return accessDenied(user, "Placement officer not found");
    report = await serverApi<Report>(memberReportUrl(userId, period, start));
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return accessDenied(user!, "That placement officer is not in your team.");
    return accessUnavailable(e, RECRUITER_SIGN_IN);
  }
  const { nav, roleLabel } = companyShell(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Activity reports</div>
            <h2>{report.recruiter.full_name} — {periodLabel(period, report.period_start, report.period_end)}</h2>
            <p className="muted"><a href={`${MANAGER_REPORTS_PATH}?period=${period}&start=${report.period_start}`}>All team reports</a></p>
          </div>
        </div>
        <PoActivityReport report={report} canSubmit={false} recruiterId={userId} />
      </div>
    </PortalShell>
  );
}
