import SchoolStudentTimeline, { loadStudentTimeline } from "@/components/SchoolStudentTimeline";
import { formatDate } from "@/components/SchoolChildOverview";

// Shared read-only student header + Journey Timeline, reused across every School role that
// can open one student's page within their own SCH-001 scope: Teacher (assigned), School
// Coordinator and Principal (own institution). Each role keeps its own thin page/route
// (matching this app's existing per-role-route convention -- see SchoolServiceDeliverySummary
// for the same reuse pattern across dashboards) -- only this presentational piece is shared,
// so no role gains another role's write actions by using it.

type Student = { id: string; student_code: string; full_name: string; date_of_birth: string | null; grade_or_class: string | null };

export default async function SchoolStudentDetailPanel({ student, backHref, backLabel }: { student: Student; backHref: string; backLabel: string }) {
  const timeline = await loadStudentTimeline(student.id).catch(() => null);
  return (
    <div className="portal-content">
      <div className="card">
        <h2>{student.full_name} <span className="muted" style={{ fontSize: 14 }}>({student.student_code})</span></h2>
        <p><strong>Grade/Class:</strong> {student.grade_or_class || "-"}</p>
        <p><strong>Date of birth:</strong> {formatDate(student.date_of_birth)}</p>
        <a className="btn secondary" href={backHref}>{backLabel}</a>
      </div>
      <div className="card">
        <h3>Journey timeline</h3>
        {timeline ? <SchoolStudentTimeline events={timeline.events} /> : <p className="muted">Timeline is unavailable right now.</p>}
      </div>
    </div>
  );
}
