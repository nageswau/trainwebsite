import type { AverageRow, PerformerRow, StudentDevelopment } from "@/lib/types";

// ENH-016 (School CRM.md Part B §14). Pending = total - completed (D2). Academic figures count published results only
// (SCH-006-AC02); the thresholds are a plain GET form, so they live in the URL and work without client JS.
function Averages({ title, rows }: { title: string; rows: AverageRow[] }) {
  if (rows.length === 0) return null;
  return (
    <div className="table-scroll">
      <table className="table">
        <caption>{title}</caption>
        <thead>
          <tr><th scope="col">Group</th><th scope="col">Average</th><th scope="col">Results</th></tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key}>
              <th scope="row">{r.label}</th>
              <td>{r.average_pct === null ? "—" : `${r.average_pct}%`}</td>
              <td>{r.count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Performers({ label, rows, total, empty }: { label: string; rows: PerformerRow[]; total: number; empty: string }) {
  return (
    <section aria-label={label}>
      <h3>{label} ({total})</h3>
      {rows.length === 0 ? (
        <p className="muted">{empty}</p>
      ) : (
        <ul aria-label={label}>
          {rows.map((p) => (
            <li key={p.school_student_id}>{p.full_name} · Grade {p.grade} · {p.average_pct}% ({p.result_count} results)</li>
          ))}
        </ul>
      )}
      {total > rows.length && <p className="muted">Showing the first {rows.length}.</p>}
    </section>
  );
}

export default function SchoolStudentDevelopment({ data, basePath }: { data: StudentDevelopment; basePath: string }) {
  const hasResults = data.by_subject.length > 0;
  return (
    <div className="card">
      <h2>Student development</h2>
      <p>{data.headcounts.students} students · {data.headcounts.teachers} teachers · {data.headcounts.parents} parents</p>
      <div className="table-scroll">
        <table className="table">
          <caption className="sr-only">Student development</caption>
          <thead>
            <tr><th scope="col">Activity</th><th scope="col">Completed</th><th scope="col">Pending</th></tr>
          </thead>
          <tbody>
            {data.activities.map((a) => (
              <tr key={a.key}>
                <th scope="row">{a.label}</th>
                <td>{a.completed}</td>
                <td>{a.pending}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h3>Academic performance</h3>
      {!hasResults ? (
        <p className="muted">No published results yet.</p>
      ) : (
        <>
          <Averages title="By grade" rows={data.by_grade.map((r) => ({ ...r, label: `Grade ${r.label}` }))} />
          <Averages title="By subject" rows={data.by_subject} />
          <Averages title="By term" rows={data.by_term} />
        </>
      )}
      <form method="get" action={`${basePath}#development`} className="analytics-form">
        <div className="field">
          <label htmlFor="at_risk_below">At risk below (%)</label>
          <input id="at_risk_below" name="at_risk_below" type="number" min={0} max={100} defaultValue={data.at_risk_below} />
        </div>
        <div className="field">
          <label htmlFor="top_from">Top performer from (%)</label>
          <input id="top_from" name="top_from" type="number" min={0} max={100} defaultValue={data.top_from} />
        </div>
        <button className="btn secondary" type="submit">Update thresholds</button>
      </form>
      <Performers label="At-risk students" rows={data.at_risk.items} total={data.at_risk.total} empty={`No students below ${data.at_risk_below}%.`} />
      <Performers label="Top performers" rows={data.top_performers.items} total={data.top_performers.total} empty={`No students at or above ${data.top_from}% yet.`} />
    </div>
  );
}
