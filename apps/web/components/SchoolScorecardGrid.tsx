import { ScorecardStateBadge } from "@/components/StudentScorecard";
import type { ScorecardPage } from "@/lib/types";

// ENH-016 (School CRM.md §28, D10): every student × area, filtered and paged through the URL so it works without client JS.
function pageHref(basePath: string, grade: string, offset: number) {
  const params = new URLSearchParams();
  if (grade) params.set("grade", grade);
  if (offset > 0) params.set("offset", String(offset));
  const query = params.toString();
  return `${basePath}${query ? `?${query}` : ""}#scorecards`;
}

export default function SchoolScorecardGrid({ page, grade, basePath, studentHref }: { page: ScorecardPage; grade: string; basePath: string; studentHref: (id: string) => string }) {
  const areas = page.items[0]?.areas ?? [];
  const prev = page.offset > 0 ? Math.max(0, page.offset - page.limit) : null;
  const next = page.offset + page.limit < page.total ? page.offset + page.limit : null;
  const shown = page.items.length === 0 ? `${page.total} students` : `${page.offset + 1}–${page.offset + page.items.length} of ${page.total}`;
  return (
    <div className="card" id="scorecards">
      <h2>Student progress scorecards</h2>
      <form method="get" action={`${basePath}#scorecards`} className="analytics-form">
        <div className="field">
          <label htmlFor="scorecard-grade">Grade</label>
          <select id="scorecard-grade" name="grade" defaultValue={grade}>
            <option value="">All grades</option>
            {["8", "9", "10", "11", "12"].map((g) => <option key={g} value={g}>Grade {g}</option>)}
          </select>
        </div>
        <button className="btn secondary" type="submit">Show</button>
      </form>
      {page.items.length === 0 ? (
        <p className="muted">No students match this grade.</p>
      ) : (
        <div className="table-scroll">
          <table className="table">
            <caption className="sr-only">Progress scorecards, {page.total} students</caption>
            <thead>
              <tr>
                <th scope="col">Student</th>
                {areas.map((a) => <th scope="col" key={a.key}>{a.label}</th>)}
              </tr>
            </thead>
            <tbody>
              {page.items.map((c) => (
                <tr key={c.school_student_id}>
                  <th scope="row"><a href={studentHref(c.school_student_id)}>{c.full_name}</a></th>
                  {c.areas.map((a) => <td key={a.key}><ScorecardStateBadge state={a.state} /></td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <nav className="pager" aria-label="Scorecard pages">
        {prev !== null && <a href={pageHref(basePath, grade, prev)} aria-label="Previous page">← Previous</a>}
        <span className="muted">{shown}</span>
        {next !== null && <a href={pageHref(basePath, grade, next)} aria-label="Next page">Next →</a>}
      </nav>
    </div>
  );
}
