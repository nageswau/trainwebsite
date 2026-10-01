import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import SchoolDailyAttendance, { type DailyRoster } from "@/components/SchoolDailyAttendance";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

// ENH-030 (DEC-SCOPE-041): the teacher marks their assigned class for one day. The server scopes the roster (assigned students
// only) and decides "today" on the school calendar; only a real calendar date in YYYY-MM-DD form is passed on -- anything else
// (malformed, or well-formed but impossible like 2026-02-30, QA30-03) falls back to the school's today.
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function calendarDate(raw: string | string[] | undefined): string | null {
  // Year 0000 is valid ISO but outside the server's date range (years 1-9999), which would answer with a validation list (review M-5).
  if (typeof raw !== "string" || !ISO_DATE.test(raw) || raw.startsWith("0000")) return null;
  const parsed = new Date(`${raw}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === raw ? raw : null;
}

export default async function SchoolTeacherAttendancePage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const day = calendarDate((await searchParams).date);
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
