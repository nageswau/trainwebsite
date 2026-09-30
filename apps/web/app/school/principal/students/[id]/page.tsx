import PortalShell from "@/components/PortalShell";
import ReportDownloadButton from "@/components/ReportDownloadButton";
import SchoolStudentDetailPanel from "@/components/SchoolStudentDetailPanel";
import SectionUnavailable from "@/components/SectionUnavailable";
import StudentScorecard from "@/components/StudentScorecard";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { Scorecard, User } from "@/lib/types";

type Student = { id: string; student_code: string; full_name: string; date_of_birth: string | null; grade_or_class: string | null };

// SCH-008 (DEC-SCOPE-016): Principal's read-only view of one student's Journey Timeline,
// own institution only (SCH-001-AC02) -- reachable from the dashboard's roster table.
export default async function SchoolPrincipalStudentDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let user: User;
  let student: Student;
  let scorecard: Scorecard | null;
  try {
    // ENH-016 (§28, D9): the scorecard is read on its own; if it fails, the rest of the page still renders.
    [user, student, scorecard] = await Promise.all([
      serverApi<User>("/api/v1/auth/me"),
      serverApi<Student>(`/api/v1/school/students/${id}`),
      serverApi<Scorecard>(`/api/v1/school/students/${id}/scorecard`).catch(() => null),
    ]);
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
      <SchoolStudentDetailPanel student={student} role="school_principal" backHref="/school/principal/dashboard" backLabel="Back to dashboard" />
      {/* ENH-015: this student's overview as a PDF (same scope as the overview). */}
      <div className="portal-content report-downloads">
        <div className="card">
          <h2>Progress report</h2>
          <p className="muted">A PDF of this student&apos;s profile and progress to date.</p>
          <ReportDownloadButton url={`/api/v1/school/students/${student.id}/progress-report`} label="Download progress report (PDF)" filename="progress-report.pdf" />
        </div>
      </div>
      <div className="portal-content">{scorecard ? <StudentScorecard card={scorecard} /> : <SectionUnavailable title="Progress scorecard" />}</div>
    </PortalShell>
  );
}
