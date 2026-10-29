import Link from "next/link";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { HR_STUDENTS_API, HR_STUDENTS_PATH, hrStudentsQuery, type HrStudentList } from "@/lib/hrStudents";
import { PORTAL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

const UNAVAILABLE = "The student list is unavailable right now. Please try again.";

// nehn-017 (DEC-SCOPE-310): HR's students -- the active placement pool, read only. The API decides who is listed and refuses a caller
// without `student_progress.view`; the role check here only spares other roles a screen that can only fail.
export default async function HrStudentsPage({ searchParams }: { searchParams: Record<string, string | string[] | undefined> }) {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/it/login");
  }
  if (user.role !== "hr_team") return accessDenied(user, "HR role required");
  const q = (typeof searchParams.q === "string" ? searchParams.q : "").trim().slice(0, 100);
  const requested = Number(typeof searchParams.page === "string" ? searchParams.page : "1");
  const page = Number.isInteger(requested) && requested >= 1 && requested <= 10000 ? requested : 1;
  let list: HrStudentList | null = null;
  let error = "";
  try {
    list = await serverApi<HrStudentList>(`${HR_STUDENTS_API}${hrStudentsQuery(q, page)}`);
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return accessUnavailable(e, "/it/login");
    error = UNAVAILABLE;
  }
  const pages = list ? Math.max(1, Math.ceil(list.total / list.page_size)) : 1;
  return (
    <PortalShell nav={PORTAL_NAV["it/hr"]} roleLabel="HR Team" userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Students</div>
            <h2>Students</h2>
            <p className="muted">Training progress, completion, attendance and selected documents of the students in the placement pool. Read only.</p>
          </div>
        </div>
        <div className="action-card">
          <form method="get" action={HR_STUDENTS_PATH} role="search" aria-label="Search students" autoComplete="off" className="analytics-form">
            <div className="field" style={{ margin: 0, flex: "1 1 260px" }}>
              <label htmlFor="hr-student-q">Student ID, name or email</label>
              <input id="hr-student-q" className="input" type="search" name="q" defaultValue={q} maxLength={100} />
            </div>
            <button className="btn small">Search</button>
            {q && <Link className="btn small secondary" href={HR_STUDENTS_PATH}>Clear</Link>}
          </form>
          {error && <p className="form-error" role="alert">{error}</p>}
          {list && (list.items.length === 0 ? (
            <p className="muted">{q ? `No students match “${q}”.` : "No students are in the placement pool yet."}</p>
          ) : (
            <>
              <p className="muted" aria-live="polite">{list.total} student{list.total === 1 ? "" : "s"}{q ? ` matching “${q}”` : ""}</p>
              <div className="table-wrap">
                <table className="table stack compact hr-student-table" aria-label="Students">
                  <thead><tr><th scope="col">Student</th><th scope="col">Student ID</th><th scope="col">Courses</th><th scope="col">Completed</th></tr></thead>
                  <tbody>
                    {list.items.map((s) => (
                      <tr key={s.id}>
                        <th scope="row" data-label="Student"><Link href={`${HR_STUDENTS_PATH}/${s.id}`}>{s.full_name}</Link></th>
                        <td data-label="Student ID">{s.student_code ?? "—"}</td>
                        <td data-label="Courses">{s.courses}</td>
                        <td data-label="Completed">{s.completed}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {pages > 1 && (
                <nav aria-label="Pages" style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 12 }}>
                  {list.page > 1 && <Link className="btn small secondary" href={`${HR_STUDENTS_PATH}${hrStudentsQuery(q, list.page - 1)}`}>Previous</Link>}
                  <span className="muted">Page {list.page} of {pages}</span>
                  {list.page < pages && <Link className="btn small secondary" href={`${HR_STUDENTS_PATH}${hrStudentsQuery(q, list.page + 1)}`}>Next</Link>}
                </nav>
              )}
            </>
          ))}
        </div>
      </div>
    </PortalShell>
  );
}
