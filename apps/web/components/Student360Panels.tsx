import type { ReactNode } from "react";

import CareerGoalForm from "@/components/CareerGoalForm";
import { type ChildOverview, SkillsCard, StatusChip } from "@/components/SchoolChildOverview";
import SchoolGradeHistory, { type GradeHistoryEntry } from "@/components/SchoolGradeHistory";
import { formatDate } from "@/lib/formatDate";
import type { Student360, Tab360 } from "@/lib/student360";
import { safeHref, TAB_LABELS, type TabKey } from "@/lib/student360Links";

// ENH-013 -- one small presentational body per tab (docs/superpowers/specs/2026-09-23-enh-013a-student-360-view-design.md §8).
// Every tab has three shapes: restricted (the viewer's role cannot read this source through any other screen, so not here either),
// empty (a state that says who records the data), or data. Server-rendered and handed to Student360Tabs as its children.

/* eslint-disable @typescript-eslint/no-explicit-any -- tab `data` is a per-tab shape documented in spec §6.3; typed at the edges. */
type Row = Record<string, any>;
type Entry = { id: string; title: string; organization: string | null; date_from: string | null; date_to: string | null; description: string | null };

const EMPTY_TEXT: Record<TabKey, string> = {
  overview: "No achievements recorded yet.",
  personal_details: "",
  academic_records: "No grade changes yet. They appear here after the student's first promotion.",
  attendance: "No attendance recorded yet. The School Coordinator marks activity attendance.",
  examination_results: "No published results yet. Results appear after the Academic Team publishes them.",
  career_guidance: "No career guidance recorded yet. The Career Counselor adds sessions and notes.",
  psychometric_assessment: "No psychometric assessments yet. The Psychometric Team assigns them.",
  skills: "No skills recorded yet.",
  foreign_languages: "No foreign language classes recorded yet.",
  english_testing: "No English test preparation recorded yet.",
  activities: "No activities recorded yet.",
  certificates: "No certificates recorded yet. Staff add them in the Digital Portfolio.",
  documents: "No documents yet.",
  teacher_remarks: "No teacher remarks on published results yet.",
  parent_communication: "No parent communication log yet.",
  edusphere_programs: "Not enrolled in any EduSphere programme yet.",
};
const RECORD_TYPE: Record<string, string> = { guidance_session: "Guidance session", counselling_note: "Counselling note", recommendation: "Career recommendation" };
const PROGRAMME: Record<string, string> = { soft_skills: "Soft Skills", digital_skills: "Digital Skills", test_prep: "Test preparation", foreign_language: "Foreign languages", global_education: "Global education" };
const PROGRAMME_STATUS: Record<string, string> = { linked: "Application linked" };
const ACTIVITY_SECTION: Record<string, string> = { project: "Projects", internship: "Internships", sport: "Sports", leadership: "Leadership", volunteering: "Volunteering", extracurricular: "Extracurriculars" };

const Card = ({ children }: { children: ReactNode }) => <div className="card">{children}</div>;
const Empty = ({ text }: { text: string }) => <p className="empty" role="status">{text}</p>;

function Entries({ entries }: { entries: Entry[] }) {
  return (
    <ul className="s360-list">
      {entries.map((e) => (
        <li key={e.id}>
          <strong>{e.title}</strong>{e.organization ? <span className="muted"> — {e.organization}</span> : null}
          {e.date_from ? <span className="muted"> ({formatDate(e.date_from)}{e.date_to ? ` – ${formatDate(e.date_to)}` : ""})</span> : null}
          {e.description ? <p>{e.description}</p> : null}
        </li>
      ))}
    </ul>
  );
}

// A table is named either by a visually hidden `caption` or, when a visible heading already says the same thing, by that heading
// (`labelledBy`) -- never both, or screen readers announce the name twice (browser QA-06).
function Table({ caption, labelledBy, head, rows }: { caption?: string; labelledBy?: string; head: string[]; rows: ReactNode[][] }) {
  return (
    <div className="table-wrap">
      <table className="table" aria-labelledby={labelledBy}>
        {caption ? <caption className="visually-hidden">{caption}</caption> : null}
        <thead><tr>{head.map((h) => <th key={h} scope="col">{h}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}>{c ?? "-"}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

function Facts({ facts }: { facts: [string, ReactNode][] }) {
  return <dl className="s360-facts">{facts.map(([k, v]) => <div key={k}><dt className="muted">{k}</dt><dd>{v}</dd></div>)}</dl>;
}

function body(key: TabKey, d: Row, view: Student360): ReactNode {
  switch (key) {
    case "overview":
      return (
        <>
          <Card>
            <h3>Career goal</h3>
            {view.can_edit_career_goal ? <CareerGoalForm studentId={view.student.id} goal={view.career_goal} /> : <p>{view.career_goal ?? <span className="muted">No career goal set yet.</span>}</p>}
          </Card>
          <Card>
            <h3>Achievements</h3>
            {d.achievements.length ? <Entries entries={d.achievements} /> : <p className="muted">{EMPTY_TEXT.overview}</p>}
            <p className="muted">Digital Portfolio {d.portfolio_completion_percentage}% complete.</p>
          </Card>
        </>
      );
    case "personal_details": {
      const facts: [string, ReactNode][] = [["Name", d.full_name], ["Student ID", d.student_code], ["Grade/Class", d.grade_or_class], ["Date of birth", d.date_of_birth ? formatDate(d.date_of_birth) : null], ["School", d.school_name], ["Assigned teacher", d.assigned_teacher_name]];
      return <Card><Facts facts={facts.filter(([, v]) => v !== null && v !== undefined)} /></Card>;
    }
    case "academic_records":
      return <Card><p><strong>Current grade/class:</strong> {d.grade_or_class ?? "-"}</p>{d.grade_history.length ? <SchoolGradeHistory history={d.grade_history as GradeHistoryEntry[]} /> : <Empty text={EMPTY_TEXT.academic_records} />}</Card>;
    case "attendance":
      return (
        <Card>
          {d.activities.length ? <Table caption="School activity attendance" head={["Activity", "Date", "Attendance"]} rows={d.activities.map((a: Row) => [a.title, formatDate(a.scheduled_at), a.present ? "Present" : "Absent"])} /> : null}
          {d.skill_sessions.length ? <Table caption="Skills session attendance" head={["Skills batch", "Sessions attended"]} rows={d.skill_sessions.map((s: Row) => [s.batch_title, `${s.present} of ${s.marked}`])} /> : null}
        </Card>
      );
    case "examination_results":
      return <Card><Table caption="Published results" head={["Year", "Term", "Subject", "Marks", "Grade"]} rows={d.results.map((r: Row) => [r.academic_year, r.term, r.subject, r.max_marks !== undefined ? `${r.marks_obtained} / ${r.max_marks}` : null, r.grade])} /></Card>;
    case "career_guidance":
      return <Card><ul className="s360-list">{d.records.map((r: Row) => <li key={r.id}><strong>{RECORD_TYPE[r.record_type] ?? r.record_type}</strong> <span className="muted">{formatDate(r.created_at)}</span><p>{r.notes}</p></li>)}</ul></Card>;
    case "psychometric_assessment":
      return <Card><Table caption="Psychometric assessments" head={["Assessment", "Status", "Date"]} rows={d.assessments.map((a: Row) => [a.assessment_type, a.status ? <StatusChip status={a.status} /> : null, formatDate(a.created_at)])} /></Card>;
    case "skills":
      return (
        <>
          {d.batches ? <SkillsCard skills={d.batches as NonNullable<ChildOverview["skills"]>} /> : null}
          {d.portfolio_entries.length ? <Card><h3>Skills in the Digital Portfolio</h3><Entries entries={d.portfolio_entries} /></Card> : null}
        </>
      );
    case "foreign_languages":
      return <Card><Table caption="Foreign languages" head={["Language", "Level", "Certification"]} rows={d.records.map((r: Row) => [r.language, r.level, <StatusChip key="c" status={r.certification_status} />])} /></Card>;
    case "english_testing":
      return <Card><Table caption="English test preparation" head={["Test", "Target", "Result", "Status"]} rows={d.records.map((r: Row) => [String(r.test_type).toUpperCase(), r.target_score, r.actual_score, <StatusChip key="s" status={r.status} />])} /></Card>;
    case "activities": {
      const attended = (d.attended ?? []).filter((a: Row) => a.present);
      const upcoming: Row[] = d.upcoming ?? [];  // School roles only (null for service roles); school-wide, not the student's record
      const sections = Object.entries(d.portfolio_entries as Record<string, Entry[]>).filter(([, v]) => v.length);
      return (
        <>
          {!attended.length && !sections.length ? <Card><Empty text={EMPTY_TEXT.activities} /></Card> : null}
          {attended.length ? <Card><h3 id="s360-attended">School activities attended</h3><Table labelledBy="s360-attended" head={["Activity", "Date"]} rows={attended.map((a: Row) => [a.title, formatDate(a.scheduled_at)])} /></Card> : null}
          {sections.map(([section, v]) => <Card key={section}><h3>{ACTIVITY_SECTION[section] ?? section}</h3><Entries entries={v} /></Card>)}
          {upcoming.length ? <Card><h3 id="s360-upcoming">Upcoming school activities</h3><Table labelledBy="s360-upcoming" head={["Activity", "Date"]} rows={upcoming.map((a) => [a.title, formatDate(a.scheduled_at)])} /></Card> : null}
        </>
      );
    }
    case "certificates":
      return <Card><Entries entries={d.entries} /></Card>;
    case "documents":
      return (
        <Card>
          <ul className="s360-list">
            {d.psychometric_reports.map((r: Row, i: number) => {
              const href = safeHref(r.report_url);
              return (
                <li key={i}>
                  {href ? <a href={href} target="_blank" rel="noopener noreferrer">{r.assessment_type} report</a> : <>{r.assessment_type} report: <span className="muted">{r.report_url}</span></>}
                  {" "}<span className="muted">{formatDate(r.created_at)}</span>
                </li>
              );
            })}
          </ul>
        </Card>
      );
    case "teacher_remarks":
      return <Card><ul className="s360-list">{d.remarks.map((r: Row) => <li key={r.id}><strong>{r.subject}</strong> <span className="muted">{r.academic_year} · {r.term}</span><p>{r.teacher_remarks}</p></li>)}</ul></Card>;
    case "edusphere_programs":
      return (
        <Card>
          <ul className="s360-list">
            {d.programmes.map((p: Row) => (
              <li key={p.key}><strong>{PROGRAMME[p.key] ?? p.key}</strong> {PROGRAMME_STATUS[p.status] ? <span className="status pending">{PROGRAMME_STATUS[p.status]}</span> : <StatusChip status={p.status} />}</li>
            ))}
          </ul>
        </Card>
      );
    default:
      return null;
  }
}

// Tabs whose body is meaningful even with no records: the overview (career goal), identity, the current grade, and activities
// (upcoming school activities are shown before the student has any record of their own; the body renders its own empty state).
const ALWAYS_SHOW_BODY: ReadonlySet<TabKey> = new Set(["overview", "personal_details", "academic_records", "activities"]);

export function renderPanel(key: TabKey, tab: Tab360, view: Student360): ReactNode {
  let content: ReactNode;
  if (tab.status === "restricted") content = <Card><Empty text="This section is not available for your role." /></Card>;
  else if (tab.status === "empty" && !ALWAYS_SHOW_BODY.has(key)) content = <Card><Empty text={EMPTY_TEXT[key]} /></Card>;
  else content = body(key, tab.data as Row, view);
  return (
    <section className="s360-section" aria-labelledby={`s360-h-${key}`}>
      <h2 id={`s360-h-${key}`}>{TAB_LABELS[key]}</h2>
      {content}
      {tab.not_tracked.length ? <p className="muted">{tab.not_tracked.join(" ")}</p> : null}
    </section>
  );
}
