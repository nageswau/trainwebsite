import { accessUnavailable } from "@/components/AccessUnavailable";
import BdmCalendar from "@/components/BdmCalendar";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { BDM_TYPE_LABEL, type BdmMe } from "@/lib/bdm";
import { todayIst } from "@/lib/bdmAppointments";
import { apiPath, type CalendarData, isCalendarData, parseDate, parseView, rangeOf } from "@/lib/bdmCalendar";
import { bdmNav } from "@/lib/bdmNav";
import { BDM_SIGN_IN } from "@/lib/navigation";

type Search = Promise<{ view?: string | string[]; date?: string | string[] }>;

// bdm-013: the BDM's own calendar, day or week (?view=day|week&date=YYYY-MM-DD). The API is the gate; a calendar read that fails
// after the profile loaded is shown inline with "Try again".
export default async function BdmCalendarPage({ searchParams }: { searchParams: Search }) {
  const nav = bdmNav(); // the unread badge, read alongside the page's own data (never rejects)
  const params = await searchParams;
  let me: BdmMe;
  try {
    me = await serverApi<BdmMe>("/api/v1/bdm/me");
  } catch (e) {
    return accessUnavailable(e, BDM_SIGN_IN);
  }
  const view = parseView(params.view);
  const date = parseDate(params.date, todayIst());
  const { from, to } = rangeOf(view, date);
  const data = await serverApi<CalendarData>(apiPath(from, to)).then((d) => (isCalendarData(d) ? d : null), () => null);
  return (
    <PortalShell nav={await nav} roleLabel={`${BDM_TYPE_LABEL[me.bdm_profile.bdm_type]} BDM`} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Calendar</div>
            <h2>Your calendar</h2>
            <p className="muted">Appointments, travel, follow-ups and tasks. Read-only; open an item to change it. Times are India time (IST).</p>
          </div>
        </div>
        <BdmCalendar data={data} view={view} date={date} basePath="/bdm/calendar" managerOf={null} />
      </div>
    </PortalShell>
  );
}
