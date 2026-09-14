import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

type Student = { id: string; full_name: string; date_of_birth: string | null; grade_or_class: string | null };

// SCH-001: one assigned student's detail, read-only. Same assigned-scope deny as the
// dashboard, verified server-side even via this direct record ID (SCH-001-AC03).
export default async function SchoolTeacherStudentDetailPage({ params }: { params: Promise<{ id: string }> }) {
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
          <p>{e instanceof Error ? e.message : "This student is not assigned to you, or does not exist."}</p>
          <a className="btn" href="/school/teacher/dashboard">Back to your students</a>
        </div>
      </div>
    );
  }
  return (
    <PortalShell nav={SCHOOL_NAV.teacher} roleLabel="Teacher" userName={user.full_name}>
      <div className="portal-content">
        <div className="card">
          <h2>{student.full_name}</h2>
          <p><strong>Grade/Class:</strong> {student.grade_or_class || "-"}</p>
          <p><strong>Date of birth:</strong> {student.date_of_birth || "-"}</p>
          <a className="btn secondary" href="/school/teacher/dashboard">Back to your students</a>
        </div>
      </div>
    </PortalShell>
  );
}
