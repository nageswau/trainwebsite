import CampusCalendar, { TpoWidget } from "@/components/CampusCalendar";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { todayIst } from "@/lib/bdmAppointments";
import { calendarQuery, CAMPUS_CALENDAR_URL, CAMPUS_SUMMARY_URL, type CampusCalendarData, type CampusSummary, isCalendarData, isSummary, monthRange } from "@/lib/campusPlacement";
import type { NavItem } from "@/lib/navigation";

// pob-015 (V8/V10): the body both campus calendar pages share -- the TPO widget, then the month's entries. A failed read is shown inline.
export default async function CampusCalendarPage({ month: wanted, nav, roleLabel, userName, basePath, collegePath }: {
  month: string | undefined; nav: NavItem[]; roleLabel: string; userName: string; basePath: string; collegePath: (orgId: string) => string;
}) {
  const range = monthRange(wanted) ?? monthRange(todayIst().slice(0, 7))!;
  const month = range.from.slice(0, 7);
  const [data, summary] = await Promise.all([
    serverApi<CampusCalendarData>(`${CAMPUS_CALENDAR_URL}?${calendarQuery(range)}`).then((d) => (isCalendarData(d) ? d : null), () => null),
    serverApi<CampusSummary>(CAMPUS_SUMMARY_URL).then((d) => (isSummary(d) ? d : null), () => null),
  ]);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={userName}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Colleges</div>
            <h2>Campus calendar</h2>
            <p className="muted">Campus drives, college placement calendars and graduating batches of the colleges you work with.</p>
          </div>
        </div>
        <TpoWidget summary={summary} />
        <CampusCalendar data={data} month={month} basePath={basePath} collegePath={collegePath} />
      </div>
    </PortalShell>
  );
}
