import PortalShell from "@/components/PortalShell";
import SchoolStudentDetailPanel from "@/components/SchoolStudentDetailPanel";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

type Student = { id: string; full_name: string; date_of_birth: string | null; grade_or_class: string | null };

// SCH-008 (DEC-SCOPE-016): Principal's read-only view of one student's Journey Timeline,
// own institution only (SCH-001-AC02) -- reachable from the dashboard's roster table.
export default async function SchoolPrincipalStudentDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let user: User;
  let student: Student;
  try {
    [user, student] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<Student>(`/api/v1/school/students/${id}`)]);
  } catch (e) {
    return (
      <div className="section">
        <div className="container card">
          <h1>Access unavailable</h1>
          <p>{e instanceof Error ? e.message : "This student is at a different institution, or does not exist."}</p>
          <a className="btn" href="/school/principal/dashboard">Back to dashboard</a>
        </div>
      </div>
    );
  }
  return (
    <PortalShell nav={SCHOOL_NAV.principal} roleLabel="Principal" userName={user.full_name}>
      <SchoolStudentDetailPanel student={student} backHref="/school/principal/dashboard" backLabel="Back to dashboard" />
    </PortalShell>
  );
}
