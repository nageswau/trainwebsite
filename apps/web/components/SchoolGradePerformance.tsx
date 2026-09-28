import type { GradePerformance } from "@/lib/types";

// ENH-016 (School CRM.md §29): the same metrics side by side for each grade. Estimated metrics (D5) show their definition.
const gradeLabel = (g: string) => (g === "other" ? "Other grades" : g === "unspecified" ? "No grade" : `Grade ${g}`);

export default function SchoolGradePerformance({ data }: { data: GradePerformance }) {
  return (
    <div className="card">
      <h2>Grade-wise comparison</h2>
      {data.grades.length === 0 ? (
        <p className="muted">No students on the roster yet.</p>
      ) : (
        <div className="table-scroll">
          <table className="table">
            <caption className="visually-hidden">Grade-wise comparison</caption>
            <thead>
              <tr>
                <th scope="col">Metric</th>
                {data.grades.map((g) => <th scope="col" key={g}>{gradeLabel(g)}</th>)}
              </tr>
            </thead>
            <tbody>
              <tr>
                <th scope="row">Students</th>
                {data.grades.map((g) => <td key={g}>{data.students[g]}</td>)}
              </tr>
              {data.metrics.map((m) => (
                <tr key={m.key}>
                  <th scope="row">
                    {m.label}
                    {m.is_proxy && <span className="kpi-note muted">Estimate: {m.definition}</span>}
                  </th>
                  {data.grades.map((g) => {
                    const cell = m.cells[g];
                    return <td key={g}>{cell.pct === null ? cell.count : `${cell.count} (${Math.round(cell.pct)}%)`}</td>;
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
