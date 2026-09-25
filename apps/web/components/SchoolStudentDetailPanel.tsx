import SchoolGradeHistory, { loadGradeHistory } from "@/components/SchoolGradeHistory";
import SchoolStudentTimeline, { loadStudentTimeline } from "@/components/SchoolStudentTimeline";
import SchoolTransferHistory, { loadTransferHistory } from "@/components/SchoolTransferHistory";
import SchoolTransferRequestForm from "@/components/SchoolTransferRequestForm";
import SchoolStudentPhoto from "@/components/SchoolStudentPhoto";
import PortfolioPanel from "@/components/PortfolioPanel";
import { serverApi } from "@/lib/api";
import { formatCalendarDate } from "@/lib/formatDate";
import type { Page } from "@/lib/apiErrors";
import type { SchoolRef, TransferRequest } from "@/lib/transfers";
import { loadPortfolio } from "@/lib/portfolio";
import { GENDER_LABEL, listText, type SchoolStudent } from "@/lib/schoolStudents";
import { student360Href } from "@/lib/student360Links";

// Shared read-only student header + Journey Timeline, reused across every School role that
// can open one student's page within their own SCH-001 scope: Teacher (assigned), School
// Coordinator and Principal (own institution). Each role keeps its own thin page/route
// (matching this app's existing per-role-route convention -- see SchoolServiceDeliverySummary
// for the same reuse pattern across dashboards) -- only this presentational piece is shared,
// so no role gains another role's write actions by using it.
// ENH-004: `showGradeHistory` (default off, so the Principal and Teacher pages are unchanged)
// adds the read-only grade-history card for the Coordinator. Both reads start together.
// ENH-005: `showTransfer` (default off, for the same reason) adds the coordinator's transfer history card and a "Request a transfer"
// disclosure. The disclosure sits right under the header, collapsed: it is a rare, consequential action, so it stays out of the way of the
// record, but at the end of a long timeline it was hard to find on a phone (browser QA N4). Its destinations and this student's pending
// request are read here, in the same Promise.all, so opening it needs no client round-trip and no loading state.

// ENH-025: the Student Master fields are optional here so a caller (or a record) without them still renders --
// every missing value reads "Not recorded". `canEditPhoto` (default off) is the coordinator's photo controls.
type Student = Pick<SchoolStudent, "id" | "student_code" | "full_name" | "date_of_birth" | "grade_or_class"> & Partial<SchoolStudent>;

// QA2-08: Grade/Class and Date of birth are rows like the rest, so an empty value reads "Not recorded" everywhere.
const PROFILE_ROWS: [string, (s: Student) => string][] = [
  ["Grade/Class", (s) => s.grade_or_class ?? ""],
  ["Date of birth", (s) => (s.date_of_birth ? formatCalendarDate(s.date_of_birth) : "")],
  ["Gender", (s) => (s.gender ? GENDER_LABEL[s.gender] ?? s.gender : "")],
  ["Section", (s) => s.section ?? ""],
  ["Roll number", (s) => s.roll_number ?? ""],
  ["Student mobile", (s) => s.student_mobile ?? ""],
  ["City", (s) => s.city ?? ""],
  ["Subjects", (s) => listText(s.subjects)],
  ["Career interests", (s) => listText(s.career_interests)],
  ["Interested in studying abroad", (s) => (s.global_education_interest == null ? "" : s.global_education_interest ? "Yes" : "No")],
  ["Preferred countries", (s) => listText(s.preferred_countries)],
  ["Preferred courses", (s) => listText(s.preferred_courses)],
];

// ENH-013: `role` (the viewer's) picks which role's Student 360° route the "Open 360° view" link goes to -- the API does the scoping.
// Optional so a caller that passes none renders exactly as before (no link).
export default async function SchoolStudentDetailPanel({ student, role, backHref, backLabel, showGradeHistory = false, showTransfer = false, canEditPhoto = false }: { student: Student; role?: string; backHref: string; backLabel: string; showGradeHistory?: boolean; showTransfer?: boolean; canEditPhoto?: boolean }) {
  const view360 = role ? student360Href(role, student.id) : null;
  const [timeline, gradeHistory, transferHistory, destinations, pendingPage, portfolio] = await Promise.all([
    loadStudentTimeline(student.id).catch(() => null),
    showGradeHistory ? loadGradeHistory(student.id).catch(() => null) : Promise.resolve(null),
    showTransfer ? loadTransferHistory(student.id) : Promise.resolve([]),
    showTransfer ? serverApi<SchoolRef[]>("/api/v1/school/transfer-destinations").catch(() => null) : Promise.resolve([]),
    showTransfer ? serverApi<Page<TransferRequest>>("/api/v1/school/transfer-requests?status=pending&limit=100").catch(() => null) : Promise.resolve(null),
    loadPortfolio(student.id).catch(() => null),
  ]);
  // A school has at most 50 open requests, so one page of pending requests always contains this student's if it has one. If the lookup
  // failed the form is still offered: the server refuses a duplicate with a clear message.
  const pending = pendingPage?.items.find((r) => r.student_id === student.id) ?? null;
  return (
    <div className="portal-content">
      <div className="card">
        <h2>{student.full_name} <span className="muted" style={{ fontSize: 14 }}>({student.student_code})</span></h2>
        <div className="student-profile">
          <SchoolStudentPhoto studentId={student.id} name={student.full_name} hasPhoto={Boolean(student.has_photo)} canEdit={canEditPhoto} />
          <dl>
            {PROFILE_ROWS.map(([label, value]) => {
              const shown = value(student);
              return [
                <dt key={`${label}-term`}>{label}</dt>,
                <dd key={`${label}-value`} className={shown ? undefined : "muted"}>{shown || "Not recorded"}</dd>,
              ];
            })}
          </dl>
        </div>
        {pending && <p><span className="status pending">Transfer requested</span> to {pending.to_school.name}</p>}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {view360 && <a className="btn" href={view360}>Open 360° view</a>}
          <a className="btn secondary" href={backHref}>{backLabel}</a>
        </div>
      </div>
      {showTransfer && (
        <details className="card">
          <summary><strong>Request a transfer</strong></summary>
          <SchoolTransferRequestForm studentId={student.id} destinations={destinations} pending={pending ? { to_school_name: pending.to_school.name, created_at: pending.created_at } : null} />
        </details>
      )}
      {showGradeHistory && (
        <div className="card">
          <h3>Grade history</h3>
          {gradeHistory ? <SchoolGradeHistory history={gradeHistory.history} /> : <p className="muted">Grade history is unavailable right now.</p>}
        </div>
      )}
      {showTransfer && <SchoolTransferHistory history={transferHistory} />}
      <div className="card">
        <h3>Journey timeline</h3>
        {timeline ? <SchoolStudentTimeline events={timeline.events} /> : <p className="muted">Timeline is unavailable right now.</p>}
      </div>
      {portfolio ? <PortfolioPanel data={portfolio} /> : <div className="card"><h3>Digital Portfolio</h3><p className="muted">Portfolio is unavailable right now.</p></div>}
    </div>
  );
}
