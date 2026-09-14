import { GradeBarChart, CompletionRing } from "@/components/SchoolReportCharts";

type ReportData = {
  student_count: number;
  students_with_teacher: number;
  teacher_count: number;
  parent_count: number;
  principal_count: number;
  pending_invite_count: number;
  grade_breakdown: { grade: string; count: number }[];
  career_guidance: { students_covered: number; total_students: number };
  psychometric: { completed: number; assigned_only: number; total_students: number };
  results_published: { students_covered: number; total_students: number };
  activities: { total: number; upcoming: number; past: number };
  attendance: { present: number; total: number };
};

// School Coordinator/Principal reporting view -- every figure here is computed straight
// from live School data (SchoolStudent/SchoolCareerRecord/SchoolPsychometricRecord/
// SchoolAcademicResult/SchoolActivity), never invented (DATA_MODEL.md §8). Results are
// deliberately reported as "students with a published result," not a draft/verified
// count -- SCH-006-AC02 treats an unpublished result's very existence as sensitive to
// these two roles, and that holds in aggregate here too, not just per-record.
export default function SchoolReportsPanel({ report }: { report: ReportData }) {
  const attendanceRate = report.attendance.total > 0 ? Math.round((report.attendance.present / report.attendance.total) * 100) : null;
  return (
    <div className="portal-content">
      <div className="metric-grid">
        <div className="metric"><span>Students</span><strong>{report.student_count}</strong></div>
        <div className="metric"><span>Teachers</span><strong>{report.teacher_count}</strong></div>
        <div className="metric"><span>Parents</span><strong>{report.parent_count}</strong></div>
        <div className="metric"><span>Pending invites</span><strong>{report.pending_invite_count}</strong></div>
      </div>

      <div className="card">
        <h2>Students by grade</h2>
        <GradeBarChart data={report.grade_breakdown} />
        {report.student_count > 0 && (
          <p className="muted" style={{ fontSize: 13, marginTop: 12 }}>
            {report.students_with_teacher} of {report.student_count} student{report.student_count === 1 ? "" : "s"} ha{report.student_count === 1 ? "s" : "ve"} an assigned Teacher.
          </p>
        )}
      </div>

      <div className="card">
        <h2>Service delivery completion</h2>
        <p className="muted" style={{ marginBottom: 4 }}>Share of students with at least one record in each area.</p>
        <div className="report-rings">
          <CompletionRing label="Career guidance" value={report.career_guidance.students_covered} total={report.career_guidance.total_students} color="#0755b9" />
          <CompletionRing label="Psychometric completed" value={report.psychometric.completed} total={report.psychometric.total_students} color="#0e7c86" />
          <CompletionRing label="Results published" value={report.results_published.students_covered} total={report.results_published.total_students} color="#6d28d9" />
        </div>
        {report.psychometric.assigned_only > 0 && (
          <p className="muted" style={{ fontSize: 13, marginTop: 8 }}>
            {report.psychometric.assigned_only} more assessment{report.psychometric.assigned_only === 1 ? "" : "s"} assigned, awaiting completion.
          </p>
        )}
      </div>

      <div className="card">
        <h2>Activities &amp; attendance</h2>
        <div className="metric-grid">
          <div className="metric"><span>Total activities</span><strong>{report.activities.total}</strong></div>
          <div className="metric"><span>Upcoming</span><strong>{report.activities.upcoming}</strong></div>
          <div className="metric"><span>Completed</span><strong>{report.activities.past}</strong></div>
          <div className="metric"><span>Attendance rate</span><strong>{attendanceRate !== null ? `${attendanceRate}%` : "-"}</strong></div>
        </div>
      </div>
    </div>
  );
}
