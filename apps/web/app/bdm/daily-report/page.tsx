import { accessUnavailable } from "@/components/AccessUnavailable";
import BdmDailyReport from "@/components/BdmDailyReport";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { BDM_TYPE_LABEL, type BdmMe } from "@/lib/bdm";
import { activityDay } from "@/lib/bdmActivities";
import { type DailyReport, reportUrl } from "@/lib/bdmDailyReports";
import { bdmNav } from "@/lib/bdmNav";
import { indiaToday } from "@/lib/bdmTravel";
import { formatCalendarDate } from "@/lib/formatDate";
import { BDM_SIGN_IN } from "@/lib/navigation";

const PATH = "/bdm/daily-report";

// bdm-015 (spec §6): my report for one IST day -- the live preview, then the note and Submit; a submitted day shows its snapshot.
// The date lives in the URL (a plain GET form); a malformed or future date becomes today with a note (the activities-page rule).
export default async function DailyReportPage({ searchParams }: { searchParams: Promise<{ date?: string }> }) {
  const nav = bdmNav();
  const today = indiaToday();
  const { day, note } = activityDay((await searchParams).date, today);
  let me: BdmMe, report: DailyReport;
  try {
    [me, report] = await Promise.all([serverApi<BdmMe>("/api/v1/bdm/me"), serverApi<DailyReport>(reportUrl(day))]);
  } catch (e) {
    return accessUnavailable(e, BDM_SIGN_IN);
  }
  return (
    <PortalShell nav={await nav} roleLabel={`${BDM_TYPE_LABEL[me.bdm_profile.bdm_type]} BDM`} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Daily report</div>
            <h2>Daily report — {formatCalendarDate(day)}</h2>
            <p className="muted">The day&apos;s counts come from what you recorded: activities, appointments, trips, MoUs, leads and follow-ups.</p>
            <form className="analytics-form" method="get" action={PATH} aria-label="Choose a day">
              <div className="field">
                <label htmlFor="daily-report-date">Day</label>
                <input id="daily-report-date" type="date" name="date" defaultValue={day} max={today} />
              </div>
              <button className="btn secondary" type="submit">Show</button>
            </form>
            {note && <p className="muted">{note}</p>}
          </div>
        </div>
        <BdmDailyReport key={day} initial={report} mode="bdm" />
      </div>
    </PortalShell>
  );
}
