import { serverApi } from "@/lib/api";
import { formatDate } from "@/lib/formatDate";
import { attendanceText, ENROLMENT_LABEL, MODULE_LABEL, type SkillModule } from "@/lib/skills";

// SCH-007: one child's complete picture for the Parent Portal, read from
// GET /school/students/{id}/overview (own-child scope enforced server-side, SCH-001-AC03).
// Rendered in two densities: `compact` for the dashboard's per-child card, full for
// /school/parent/children/[id]. Portfolio and overseas-education progress are deliberately
// absent -- no confirmed module produces that data yet (`DEC-SCOPE-015`); showing an empty
// section for them would imply a record set that does not exist. Skills is shown since
// ENH-011 (`DEC-SCOPE-026`): the Career Counselor's Soft Skills / Digital Skills batches.

type CareerRecord = { id: string; record_type: string; notes: string; created_at: string };
type Assessment = { id: string; assessment_type: string; status: string; created_at: string };
type Result = { id: string; academic_year: string; term: string; subject: string; max_marks: number; marks_obtained: number; percentage: number | null; grade: string | null; teacher_remarks: string | null };
type Attended = { activity_id: string; title: string; scheduled_at: string; present: boolean };
type Upcoming = { id: string; title: string; scheduled_at: string };
type SkillEnrolment = {
  id: string; batch_id: string; batch_title: string; topic: string | null; trainer_name: string | null; start_date: string; end_date: string | null;
  status: string; frozen: boolean; completed_at: string | null; certified_at: string | null; attendance: { present: number; marked: number };
  assessments: { name: string; max_score: number; score: number | null; remarks: string | null }[];
};
type SkillModuleProgress = { status: string; enrollments: SkillEnrolment[] };

export type ChildOverview = {
  student: { id: string; student_code: string; full_name: string; date_of_birth: string | null; grade_or_class: string | null; school_name: string | null; assigned_teacher_name: string | null };
  career_guidance: { status: string; sessions: CareerRecord[] };
  counselling: { status: string; notes: CareerRecord[] };
  recommended_careers: CareerRecord[];
  psychometric: { status: string; assessments: Assessment[] };
  results: Result[];
  activities: { attended: Attended[]; upcoming: Upcoming[] };
  // ENH-011. Optional: an API without it (an older deployment) renders exactly as before.
  skills?: { soft_skills: SkillModuleProgress; digital_skills: SkillModuleProgress };
};

export async function loadChildOverview(studentId: string): Promise<ChildOverview> {
  return serverApi<ChildOverview>(`/api/v1/school/students/${studentId}/overview`);
}

/** ENH-005: true when the children's known schools are not all the same. After a transfer a parent can have children at two schools, and a
 * card must then say which one; a single-school parent's page stays exactly as it was. A child whose overview did not load is ignored. */
export function childrenSpanSchools(overviews: (ChildOverview | null)[]): boolean {
  return new Set(overviews.map((o) => o?.student.school_name).filter(Boolean)).size > 1;
}

export { formatDate };

const STATUS_LABEL: Record<string, string> = {
  // ENH-011: the enrolment statuses (including "Completed") come from the skills module itself; the rest are this page's own.
  ...ENROLMENT_LABEL,
  assigned: "Assigned", not_started: "Not started", in_progress: "In progress",
};

export function StatusChip({ status }: { status: string }) {
  const tone = status === "completed" || status === "certified" ? "" : " pending";
  return <span className={`status${tone}`}>{STATUS_LABEL[status] || status}</span>;
}

export function ChildStatusRow({ overview }: { overview: ChildOverview }) {
  return (
    <div className="metric-grid">
      <div className="metric"><span>Career guidance</span><StatusChip status={overview.career_guidance.status} /></div>
      <div className="metric"><span>Counselling</span><StatusChip status={overview.counselling.status} /></div>
      <div className="metric"><span>Psychometric</span><StatusChip status={overview.psychometric.status} /></div>
      <div className="metric"><span>Published results</span><strong>{overview.results.length}</strong></div>
      {overview.skills && (
        <>
          <div className="metric"><span>Soft skills</span><StatusChip status={overview.skills.soft_skills.status} /></div>
          <div className="metric"><span>Digital skills</span><StatusChip status={overview.skills.digital_skills.status} /></div>
        </>
      )}
    </div>
  );
}

// The counselor screens' own labels, so the Parent Portal cannot word a module differently.
const SKILL_MODULES = Object.entries(MODULE_LABEL) as [SkillModule, string][];

function SkillsCard({ skills }: { skills: NonNullable<ChildOverview["skills"]> }) {
  return (
    <div className="card">
      <h3>Skills</h3>
      {SKILL_MODULES.map(([key, label]) => (
        <section key={key}>
          <h4>{label}</h4>
          {skills[key].enrollments.length === 0 ? (
            <p className="muted">Not enrolled in a {label} batch yet.</p>
          ) : (
            <ul>
              {skills[key].enrollments.map((e) => (
                <li key={e.id}>
                  <strong>{e.batch_title}</strong>{e.topic && <> · {e.topic}</>}{e.frozen && <span className="muted"> · at a previous school</span>}{" "}
                  <StatusChip status={e.status} />
                  <div className="muted">{attendanceText(e.attendance)}</div>
                  {e.assessments.length > 0 && (
                    <ul>{e.assessments.map((a) => <li key={a.name}>{a.score === null ? `${a.name}: not scored yet` : `${a.name}: ${a.score} / ${a.max_score}${a.remarks ? ` — ${a.remarks}` : ""}`}</li>)}</ul>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      ))}
    </div>
  );
}

export default function SchoolChildOverview({ overview }: { overview: ChildOverview }) {
  const s = overview.student;
  return (
    <>
      <div className="card">
        <h2>{s.full_name} <span className="muted" style={{ fontSize: 14 }}>({s.student_code})</span></h2>
        <p><strong>School:</strong> {s.school_name || "-"}</p>
        <p><strong>Grade/Class:</strong> {s.grade_or_class || "-"}</p>
        <p><strong>Date of birth:</strong> {formatDate(s.date_of_birth)}</p>
        <p><strong>Class teacher:</strong> {s.assigned_teacher_name || "Not assigned yet"}</p>
      </div>

      <ChildStatusRow overview={overview} />

      <div className="card">
        <h3>Career guidance</h3>
        {overview.career_guidance.sessions.length === 0 ? (
          <p className="muted">No career guidance session recorded yet.</p>
        ) : (
          <ul>{overview.career_guidance.sessions.map((r) => <li key={r.id}><strong>{formatDate(r.created_at)}</strong> — {r.notes}</li>)}</ul>
        )}
      </div>

      <div className="card">
        <h3>Counselling</h3>
        {overview.counselling.notes.length === 0 ? (
          <p className="muted">No counselling notes yet.</p>
        ) : (
          <ul>{overview.counselling.notes.map((r) => <li key={r.id}><strong>{formatDate(r.created_at)}</strong> — {r.notes}</li>)}</ul>
        )}
      </div>

      <div className="card">
        <h3>Recommended careers</h3>
        {overview.recommended_careers.length === 0 ? (
          <p className="muted">No career recommendation yet — this appears once the Career Counselor records one.</p>
        ) : (
          <ul>{overview.recommended_careers.map((r) => <li key={r.id}><span className="badge">{r.notes}</span> <span className="muted">{formatDate(r.created_at)}</span></li>)}</ul>
        )}
      </div>

      <div className="card">
        <h3>Psychometric assessment</h3>
        {overview.psychometric.assessments.length === 0 ? (
          <p className="muted">No psychometric assessment assigned yet.</p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Assessment</th><th>Status</th><th>Assigned on</th></tr></thead>
              <tbody>
                {overview.psychometric.assessments.map((a) => (
                  <tr key={a.id}><td>{a.assessment_type}</td><td><StatusChip status={a.status} /></td><td>{formatDate(a.created_at)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card">
        <h3>Academic results</h3>
        {overview.results.length === 0 ? (
          <p className="muted">No published results yet. A result appears here only once the school has published it.</p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th scope="col">Year</th><th scope="col">Term</th><th scope="col">Subject</th><th scope="col">Marks</th><th scope="col">%</th><th scope="col">Grade</th><th scope="col">Remarks</th></tr></thead>
              <tbody>
                {overview.results.map((r) => (
                  <tr key={r.id}><td>{r.academic_year}</td><td>{r.term}</td><td>{r.subject}</td><td>{r.marks_obtained} / {r.max_marks}</td><td>{r.percentage ?? "-"}</td><td>{r.grade || "-"}</td><td>{r.teacher_remarks || "-"}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card">
        <h3>Activities</h3>
        {overview.activities.attended.length === 0 ? (
          <p className="muted">No activity attendance recorded yet.</p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Activity</th><th>Date</th><th>Attendance</th></tr></thead>
              <tbody>
                {overview.activities.attended.map((a) => (
                  <tr key={a.activity_id}><td>{a.title}</td><td>{formatDate(a.scheduled_at, true)}</td><td><span className={`status${a.present ? "" : " error"}`}>{a.present ? "Present" : "Absent"}</span></td></tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {overview.skills && <SkillsCard skills={overview.skills} />}

      <div className="card">
        <h3>Upcoming sessions</h3>
        {overview.activities.upcoming.length === 0 ? (
          <p className="muted">Nothing scheduled yet.</p>
        ) : (
          <ul>{overview.activities.upcoming.map((a) => <li key={a.id}><strong>{formatDate(a.scheduled_at, true)}</strong> — {a.title}</li>)}</ul>
        )}
      </div>
    </>
  );
}
