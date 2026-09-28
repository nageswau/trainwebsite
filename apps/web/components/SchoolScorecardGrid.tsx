import { ScorecardStateBadge } from "@/components/StudentScorecard";
import { plural } from "@/lib/plural";
import type { ScorecardPage } from "@/lib/types";

// ENH-016 (School CRM.md §28, D10): every student × area, filtered and paged through the URL so it works without client JS.
// The thresholds of the Student development form ride along as hidden fields and in the paging links, so neither form resets
// the other (QA-016-12).
type Props = {
  page: ScorecardPage;
  grade: string;
  basePath: string;
  studentHref: (id: string) => string;
  thresholds?: Record<string, string>;
};

export default function SchoolScorecardGrid({ page, grade, basePath, studentHref, thresholds = {} }: Props) {
  const pageHref = (offset: number) => {
    const params = new URLSearchParams(thresholds);
    if (grade) params.set("grade", grade);
    if (offset > 0) params.set("offset", String(offset));
    const query = params.toString();
    return `${basePath}${query ? `?${query}` : ""}#scorecards`;
  };
  const areas = page.items[0]?.areas ?? [];
  const lastOffset = Math.max(0, Math.floor((page.total - 1) / page.limit) * page.limit);
  const pastEnd = page.items.length === 0 && page.total > 0;
  // Past the end, Previous goes to the real last page, not to another empty one (QA-016-06).
  const prev = page.offset === 0 ? null : pastEnd ? lastOffset : Math.max(0, page.offset - page.limit);
  const next = page.offset + page.limit < page.total ? page.offset + page.limit : null;
  const empty = pastEnd ? "This page is past the end of the list." : grade ? "No students match this grade." : "No students on the roster yet.";
  const shown = page.items.length === 0 ? plural(page.total, "student") : `${page.offset + 1}–${page.offset + page.items.length} of ${page.total}`;
  return (
    <div className="card" id="scorecards">
      <h2>Student progress scorecards</h2>
      <form method="get" action={`${basePath}#scorecards`} className="analytics-form">
        {Object.entries(thresholds).map(([name, value]) => <input key={name} type="hidden" name={name} value={value} />)}
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
        <p className="muted">{empty}</p>
      ) : (
        <div className="table-scroll">
          <table className="table">
            <caption className="visually-hidden">Progress scorecards, {plural(page.total, "student")}</caption>
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
        {prev !== null && <a href={pageHref(prev)} aria-label="Previous page">← Previous</a>}
        <span className="muted">{shown}</span>
        {next !== null && <a href={pageHref(next)} aria-label="Next page">Next →</a>}
      </nav>
    </div>
  );
}
