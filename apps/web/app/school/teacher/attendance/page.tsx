import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import SchoolDailyAttendance, { type DailyRoster } from "@/components/SchoolDailyAttendance";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

// ENH-030 (DEC-SCOPE-038): the teacher marks their assigned class for one day. The server scopes the roster (assigned students
// only) and decides "today" on the school calendar; only a well-formed YYYY-MM-DD is passed on.
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

export default async function SchoolTeacherAttendancePage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const raw = (await searchParams).date;
  const day = typeof raw === "string" && ISO_DATE.test(raw) ? raw : null;
  let user: User;
  let roster: DailyRoster;
  try {
    [user, roster] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<DailyRoster>(`/api/v1/school/attendance${day ? `?date=${day}` : ""}`)]);
  } catch (e) {
    return accessUnavailable(e);
  }
  return (
    <PortalShell nav={SCHOOL_NAV.teacher} roleLabel="Teacher" userName={user.full_name}>
      <div className="portal-content">
        <h1>Attendance</h1>
        <div className="card">
          {/* A new date remounts the form with that day's marks; router.refresh() after a save keeps the key, so its message stays. */}
          <SchoolDailyAttendance key={roster.session_date} roster={roster} />
        </div>
      </div>
    </PortalShell>
  );
}
