import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PoActivityReport from "@/components/PoActivityReport";
import PoPeriodPicker from "@/components/PoPeriodPicker";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { companyShell, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import { chosenPeriod, periodLabel, type Report, REPORTS_PATH, reportUrl } from "@/lib/recruiterPoWork";
import { istToday } from "@/lib/telecallerTargets";
import type { User } from "@/lib/types";

// pob-009 T7 (AC3): the PO's daily or weekly (Monday-Sunday IST) report -- auto-computed counts plus a note, submitted to the Team Lead.
export default async function ActivityReportPage({ searchParams }: { searchParams: Promise<{ period?: string; start?: string }> }) {
  const today = istToday();
  const { period, start } = chosenPeriod(await searchParams, today);
  let user: User, report: Report;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (user.role !== "placement_team") return accessDenied(user, "This page is for placement officers.");
    report = await serverApi<Report>(reportUrl(period, start));
  } catch (e) {
    return accessUnavailable(e, RECRUITER_SIGN_IN);
  }
  const { nav, roleLabel } = companyShell(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Activity reports</div>
            <h2>{period === "weekly" ? "Weekly report" : "Daily report"} — {periodLabel(period, report.period_start, report.period_end)}</h2>
            <PoPeriodPicker action={REPORTS_PATH} period={period} start={start} today={today} />
          </div>
        </div>
        <PoActivityReport key={`${period}-${start}`} report={report} canSubmit />
      </div>
    </PortalShell>
  );
}
