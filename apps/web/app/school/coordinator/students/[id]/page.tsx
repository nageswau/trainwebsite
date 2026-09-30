import Link from "next/link";
import { accessDenied } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import ReportDownloadButton from "@/components/ReportDownloadButton";
import SchoolStudentDetailPanel from "@/components/SchoolStudentDetailPanel";
import SectionUnavailable from "@/components/SectionUnavailable";
import StudentScorecard from "@/components/StudentScorecard";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { Scorecard, User } from "@/lib/types";
import type { SchoolStudent } from "@/lib/schoolStudents";

// SCH-008 (DEC-SCOPE-016): School Coordinator's read-only view of one student's Journey
// Timeline, own institution only (SCH-001-AC02) -- reachable from the roster's "Timeline"
// link. Write actions (add/edit/link parent) stay on /school/coordinator/students, not
// duplicated here.
// ENH-025 QA2-02: coordinator-only, checked before the student is read -- a Teacher who opened this URL used to get the
// coordinator shell, the transfer form and the photo controls, all of which could only fail for them. Same pattern as
// /school/coordinator/transfers (ENH-005).
export default async function SchoolCoordinatorStudentDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let user: User;
  let student: SchoolStudent;
  let scorecard: Scorecard | null;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (user.role !== "school_coordinator") return accessDenied(user, "School Coordinator role required");
    // ENH-016 (§28, D9): the scorecard is read on its own; if it fails, the rest of the page still renders.
    [student, scorecard] = await Promise.all([
      serverApi<SchoolStudent>(`/api/v1/school/students/${id}`),
      serverApi<Scorecard>(`/api/v1/school/students/${id}/scorecard`).catch(() => null),
    ]);
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
      <SchoolStudentDetailPanel student={student} role="school_coordinator" backHref="/school/coordinator/students" backLabel="Back to students" showGradeHistory showTransfer canEditPhoto />
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
