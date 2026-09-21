import Link from "next/link";
import PortalShell from "@/components/PortalShell";
import SchoolStudentDetailPanel from "@/components/SchoolStudentDetailPanel";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

type Student = { id: string; student_code: string; full_name: string; date_of_birth: string | null; grade_or_class: string | null };

// SCH-008 (DEC-SCOPE-016): School Coordinator's read-only view of one student's Journey
// Timeline, own institution only (SCH-001-AC02) -- reachable from the roster's "Timeline"
// link. Write actions (add/edit/link parent) stay on /school/coordinator/students, not
// duplicated here.
export default async function SchoolCoordinatorStudentDetailPage({ params }: { params: Promise<{ id: string }> }) {
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
          <Link className="btn" href="/school/coordinator/students">Back to students</Link>
        </div>
      </div>
    );
  }
  return (
    <PortalShell nav={SCHOOL_NAV.coordinator} roleLabel="School Coordinator" userName={user.full_name}>
      <SchoolStudentDetailPanel student={student} backHref="/school/coordinator/students" backLabel="Back to students" showGradeHistory showTransfer />
    </PortalShell>
  );
}
