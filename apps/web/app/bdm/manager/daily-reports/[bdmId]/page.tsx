import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import BdmDailyReport from "@/components/BdmDailyReport";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { BDM_TYPE_LABEL } from "@/lib/bdm";
import { activityDay } from "@/lib/bdmActivities";
import { type DailyReport, teamReportUrl } from "@/lib/bdmDailyReports";
import { bdmManagerNav } from "@/lib/bdmNav";
import { indiaToday, isUuid } from "@/lib/bdmTravel";
import { formatCalendarDate } from "@/lib/formatDate";
import type { User } from "@/lib/types";

const GRID = "/bdm/manager/daily-reports";

// bdm-015 (spec §6, R7): one team BDM's report for one IST day -- read-only, with the comment form once it is submitted. A BDM outside
// the manager's team is the API's 404 ("BDM not found").
export default async function ManagerDailyReportPage({ params, searchParams }: { params: Promise<{ bdmId: string }>; searchParams: Promise<{ date?: string }> }) {
  const nav = bdmManagerNav();
  const { bdmId } = await params;
  const today = indiaToday();
  const { day, note } = activityDay((await searchParams).date, today);
  let user: User, report: DailyReport;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (user.role !== "bdm_manager" && user.role !== "super_admin") return accessDenied(user, "This page is for BDM managers.");
    if (!isUuid(bdmId)) return accessDenied(user, "BDM not found");
    report = await serverApi<DailyReport>(teamReportUrl(bdmId, day));
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  return (
    <PortalShell nav={await nav} roleLabel={user.role === "super_admin" ? "Super Admin" : "BDM Manager"} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Daily reports</div>
            <h2>{report.bdm.full_name} — {formatCalendarDate(day)}</h2>
            <p className="muted">{BDM_TYPE_LABEL[report.bdm_type]} BDM</p>
            {note && <p className="muted">{note}</p>}
          </div>
          <a className="btn secondary no-wrap" href={`${GRID}?date=${day}`}>Back to team reports</a>
        </div>
        <BdmDailyReport key={`${bdmId}-${day}`} initial={report} mode="manager" />
      </div>
    </PortalShell>
  );
}
