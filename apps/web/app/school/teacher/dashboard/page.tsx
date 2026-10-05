import PortalShell from "@/components/PortalShell";
import SchoolServiceDeliverySummary from "@/components/SchoolServiceDeliverySummary";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";
import { accessUnavailable } from "@/components/AccessUnavailable";

type Student = { id: string; full_name: string; grade_or_class: string | null };

// SCH-001: a Teacher's own class list -- only the students actually assigned to them,
// nothing else in the school (own institution AND assigned students only, SCH-001-AC03).
export default async function SchoolTeacherDashboardPage() {
  let user: User;
  let students: Student[];
  try {
    [user, students] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<Student[]>("/api/v1/school/students")]);
  } catch (e) {
    return accessUnavailable(e);
  }
  return (
    <PortalShell nav={SCHOOL_NAV.teacher} roleLabel="Teacher" userName={user.full_name}>
      <div className="portal-content">
        <div className="card">
          <h2>Your students</h2>
          {students.length === 0 ? (
            <p className="muted">No students assigned to you yet.</p>
          ) : (
            <table className="table">
              <thead>
                <tr><th>Name</th><th>Grade/Class</th><th></th></tr>
              </thead>
              <tbody>
                {students.map((s) => (
                  <tr key={s.id}>
                    <td>{s.full_name}</td>
                    <td>{s.grade_or_class || "-"}</td>
                    <td><a className="btn ghost small" href={`/school/teacher/students/${s.id}`}>View</a></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <SchoolServiceDeliverySummary />
      </div>
    </PortalShell>
  );
}
