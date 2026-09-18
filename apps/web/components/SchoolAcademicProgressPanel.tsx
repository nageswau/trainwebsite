type ProgressRow = { school_student_id: string; full_name: string; school_name: string; result_count: number; average_percentage: number | null };

// ENH-002: portfolio-wide progress aggregate. Read-only, server-renderable (no "use client")
// -- no mutation, so no hydration cost, matching SchoolChildOverview.tsx's pattern rather
// than SchoolAcademicResultsPanel.tsx's client/actions pattern.
export default function SchoolAcademicProgressPanel({ progress }: { progress: ProgressRow[] }) {
  return (
    <div className="card">
      <h2>Portfolio progress</h2>
      {progress.length === 0 ? (
        <p className="muted">No students in your portfolio yet. Contact your Overseas Admin.</p>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th scope="col">Student</th><th scope="col">School</th><th scope="col">Results</th><th scope="col">Avg %</th></tr></thead>
            <tbody>
              {progress.map((p) => (
                <tr key={p.school_student_id}>
                  <td>{p.full_name}</td><td>{p.school_name}</td><td>{p.result_count}</td>
                  <td>{p.average_percentage === null ? "No results yet" : `${p.average_percentage}%`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
