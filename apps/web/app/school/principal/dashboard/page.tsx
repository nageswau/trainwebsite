import PortalShell from "@/components/PortalShell";
import SchoolKpiBoard from "@/components/SchoolKpiBoard";
import SchoolServiceDeliverySummary from "@/components/SchoolServiceDeliverySummary";
import SectionUnavailable from "@/components/SectionUnavailable";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { SchoolKpi, User } from "@/lib/types";
import { accessUnavailable } from "@/components/AccessUnavailable";

type Student = { id: string; full_name: string; grade_or_class: string | null };

// SCH-001: school-wide, read-only progress overview -- the one landing view a Principal
// needs. ENH-016 (DEC-SCOPE-034 D7): the School CRM.md §1 KPI board now leads it, read from
// the same /school/dashboard the Coordinator uses. Fetched on its own so a failure there
// leaves the roster below usable.
export default async function SchoolPrincipalDashboardPage() {
  let user: User;
  let students: Student[];
  let dashboard: { school_crm_kpis: SchoolKpi[] } | null;
  try {
    [user, students, dashboard] = await Promise.all([
      serverApi<User>("/api/v1/auth/me"),
      serverApi<Student[]>("/api/v1/school/students"),
      serverApi<{ school_crm_kpis: SchoolKpi[] }>("/api/v1/school/dashboard").catch(() => null),
    ]);
  } catch (e) {
    return accessUnavailable(e);
  }
  return (
    <PortalShell nav={SCHOOL_NAV.principal} roleLabel="Principal" userName={user.full_name}>
      <div className="portal-content">
        {dashboard ? <SchoolKpiBoard kpis={dashboard.school_crm_kpis} /> : <SectionUnavailable title="School at a glance" />}
        <div className="card">
          <h2>Your school</h2>
          {students.length === 0 ? (
            <p className="muted">No students yet. Ask your School Coordinator to add your first student.</p>
          ) : (
            <>
              <p>{students.length} student{students.length === 1 ? "" : "s"} on the roster.</p>
              <table className="table">
                <thead>
                  <tr><th>Name</th><th>Grade/Class</th><th></th></tr>
                </thead>
                <tbody>
                  {students.map((s) => (
                    <tr key={s.id}>
                      <td>{s.full_name}</td>
                      <td>{s.grade_or_class || "-"}</td>
                      <td><a className="btn ghost small" href={`/school/principal/students/${s.id}`}>Timeline</a></td>
                    </tr>
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
