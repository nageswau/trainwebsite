import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import StudentSearch, { type ProgramOption } from "@/components/StudentSearch";
import { ApiError, serverApi } from "@/lib/api";
import type { NavItem } from "@/lib/navigation";
import { ROLE_KINDS, studentSearchError, studentSearchFilters, studentSearchUrl, type StudentSearchResult } from "@/lib/studentSearch";
import type { User } from "@/lib/types";

const UNAVAILABLE = "Student search is unavailable right now. Please try again.";
// A FastAPI validation 422 (e.g. a hand-edited filter) has no worded detail; a worded one (the 422/429 messages) is shown as is.
const REFUSED = "This search could not be run. Check it and try again.";

// nehn-041 (DEC-SCOPE-291 S10): the one body behind /admin/student-search, /it/admin/student-search and /overseas/admin/student-search
// (a static route wins over [module]/[section]). The role check only spares other roles a screen that can only fail; the API scopes each
// kind to what the caller already sees. Only the IT-side admins can read programs, so only they get the program filter.
export default async function StudentSearchPage({ base, role, nav, roleLabel, loginHref, searchParams }: {
  base: string; role: "super_admin" | "it_admin" | "overseas_admin"; nav: NavItem[]; roleLabel: string; loginHref: string;
  searchParams: Record<string, string | string[] | undefined>;
}) {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, loginHref);
  }
  if (user.role !== role) return accessDenied(user, `${roleLabel} role required`);
  const filters = studentSearchFilters(searchParams);
  const kinds = ROLE_KINDS[role];
  const programs = kinds.includes("it_student") ? await serverApi<ProgramOption[]>("/api/v1/admin/programs").catch(() => null) : null;
  let result: StudentSearchResult | null = null;
  let error = studentSearchError(filters);
  if (filters.q && !error) {
    try {
      result = await serverApi<StudentSearchResult>(studentSearchUrl(filters));
    } catch (e) {
      if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return accessUnavailable(e, loginHref);
      error = e instanceof ApiError && (e.status === 422 || e.status === 429) ? (e.message.startsWith("[object") ? REFUSED : e.message) : UNAVAILABLE;
    }
  }
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Students</div>
            <h2>Student search</h2>
            <p className="muted">
              Find a student by Student ID, name, email, phone (any format) or course. Only students you can already see are shown, up to 20
              of each type. Pick a name to open the student.
            </p>
          </div>
        </div>
        <StudentSearch base={base} filters={filters} kinds={kinds} programs={programs} result={result} error={error} />
      </div>
    </PortalShell>
  );
}
