import PortalShell from "@/components/PortalShell";
import SchoolServiceDeliverySummary from "@/components/SchoolServiceDeliverySummary";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

type Student = { id: string; full_name: string; grade_or_class: string | null };

// SCH-001: school-wide, read-only progress overview -- the one landing view a Principal
// needs. Exact KPI set is OPEN (DEC-SCOPE-011 confirmed the role/scope, not a dashboard
// field list) -- this shows the confirmed roster only, not an invented metric set.
export default async function SchoolPrincipalDashboardPage() {
  let user: User;
  let students: Student[];
  try {
    [user, students] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<Student[]>("/api/v1/school/students")]);
  } catch (e) {
    return (
      <div className="section">
        <div className="container card">
          <h1>Access unavailable</h1>
          <p>{e instanceof Error ? e.message : "Unable to load this workspace"}</p>
          <a className="btn" href="/overseas/login">Return to login</a>
        </div>
      </div>
    );
  }
  return (
    <PortalShell nav={SCHOOL_NAV.principal} roleLabel="Principal" userName={user.full_name}>
      <div className="portal-content">
        <div className="card">
          <h2>Your school</h2>
          {students.length === 0 ? (
            <p className="muted">No students yet. Ask your School Coordinator to add your first student.</p>
          ) : (
            <>
              <p>{students.length} student{students.length === 1 ? "" : "s"} on the roster.</p>
              <table className="table">
                <thead>
                  <tr><th>Name</th><th>Grade/Class</th></tr>
                </thead>
                <tbody>
                  {students.map((s) => (
                    <tr key={s.id}><td>{s.full_name}</td><td>{s.grade_or_class || "-"}</td></tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
          <div className="field" style={{ flexDirection: "row", gap: 12, marginTop: 12 }}>
            <a className="btn secondary" href="/school/principal/reports">View full reports</a>
          </div>
        </div>
        <SchoolServiceDeliverySummary />
      </div>
    </PortalShell>
  );
}
