import ScrollIntoViewOnHash from "@/components/ScrollIntoViewOnHash";
import { plural } from "@/lib/plural";
import type { GlobalEducationPipeline } from "@/lib/types";

// ENH-017: the per-student stage list, filtered and paged through the URL so it works without client JS (the ENH-016
// SchoolScorecardGrid pattern, including QA-016-06: Previous from past the end goes to the real last page). Names are plain
// text -- this view adds no new links into student records.
type Props = { page: GlobalEducationPipeline["students"]; grade: string; basePath: string };

export default function GlobalEducationStudentTable({ page, grade, basePath }: Props) {
  const pageHref = (offset: number) => {
    const params = new URLSearchParams();
    if (grade) params.set("grade", grade);
    if (offset > 0) params.set("offset", String(offset));
    const query = params.toString();
    return `${basePath}${query ? `?${query}` : ""}#students`;
  };
  const lastOffset = Math.max(0, Math.floor((page.total - 1) / page.limit) * page.limit);
  const pastEnd = page.items.length === 0 && page.total > 0;
  const prev = page.offset === 0 ? null : pastEnd ? lastOffset : Math.max(0, page.offset - page.limit);
  const next = page.offset + page.limit < page.total ? page.offset + page.limit : null;
  const empty = pastEnd
    ? "This page is past the end of the list."
    : grade
      ? "No students in this grade are on the global education pathway."
      : "No students from this school are on the global education pathway yet. Students appear here once an EduSphere counselor links their application.";
  const shown = page.items.length === 0 ? plural(page.total, "student") : `${page.offset + 1}–${page.offset + page.items.length} of ${page.total}`;
  return (
    <div className="card" id="students">
      <ScrollIntoViewOnHash id="students" />
      <h2>Students</h2>
      <form method="get" action={`${basePath}#students`} className="analytics-form">
        <div className="field">
          <label htmlFor="pipeline-grade">Grade</label>
          <select id="pipeline-grade" name="grade" defaultValue={grade}>
            <option value="">All grades</option>
            {["8", "9", "10", "11", "12"].map((g) => <option key={g} value={g}>Grade {g}</option>)}
          </select>
        </div>
        <button className="btn secondary" type="submit">Show</button>
      </form>
      {page.items.length === 0 ? (
        <p className="muted" role="status">{empty}</p>
      ) : (
        // WCAG 2.1.1: on phones the table scrolls sideways and its cells hold no links, so the scroll box itself takes focus.
        <div className="table-scroll" tabIndex={0} role="region" aria-label="Global education students">
          <table className="table">
            <caption className="visually-hidden">Global education students, {plural(page.total, "student")}</caption>
            <thead>
              <tr><th scope="col">Student</th><th scope="col">Student ID</th><th scope="col">Grade</th><th scope="col">Furthest stage</th><th scope="col">Visa</th><th scope="col">Applications</th></tr>
            </thead>
            <tbody>
              {page.items.map((r) => (
                <tr key={r.school_student_id}>
                  <th scope="row">{r.full_name}</th>
                  <td>{r.student_code}</td>
                  <td>{/^\d+$/.test(r.grade) ? r.grade : "—"}</td>
                  <td>{r.furthest_stage_label}</td>
                  <td>{r.visa_stage_label ?? "—"}</td>
                  <td>{r.application_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <nav className="pager" aria-label="Student pages">
        {prev !== null && <a href={pageHref(prev)} aria-label="Previous page">← Previous</a>}
        <span className="muted">{shown}</span>
        {next !== null && <a href={pageHref(next)} aria-label="Next page">Next →</a>}
      </nav>
    </div>
  );
}
