import { formatDay } from "@/lib/managementDiscussions";
import { achievementClass, formatAchievement, formatTarget, type PlanChoice, type PlanProgress } from "@/lib/managementPlans";

const STATE_NOTE: Record<PlanProgress["state"], (p: PlanProgress) => string> = {
  running: (p) => `Month to date: actuals are counted live from ${formatDay(p.start)} to today.`,
  upcoming: (p) => `${p.label} starts on ${formatDay(p.start)}; actuals count from then.`,
  ended: (p) => `Final figures for ${p.label} (${formatDay(p.start)} – ${formatDay(p.end)}).`,
};

// mgmt-026 (EVID-017 §26, PN6): every KPI item's target, its live actual and the achievement, by department (vertical), then the
// free-text items' done tally. `progress` is null when the read failed.
export default function ManagementPlanProgress({ progress, error, verticals }: { progress: PlanProgress | null; error: string; verticals: PlanChoice[] }) {
  const department = (key: string) => verticals.find((v) => v.key === key)?.label ?? key;
  return (
    <section className="card" aria-labelledby="progress-title" style={{ marginBottom: 18 }}>
      <h3 id="progress-title" style={{ marginTop: 0 }}>Target vs actual</h3>
      {error && <p className="form-error" role="alert">{error}</p>}
      {progress && (
        <>
          <p className="muted" style={{ fontSize: 14 }}>{STATE_NOTE[progress.state](progress)}</p>
          {progress.rows.length === 0 ? (
            <p className="muted">No KPI items yet. Give an item a KPI and a target to track it here.</p>
          ) : (
            <div className="table-wrap" role="region" aria-labelledby="progress-title" tabIndex={0} style={{ overflowX: "auto" }}>
              <table className="table">
                <caption className="visually-hidden">Target vs actual for {progress.label}</caption>
                <thead>
                  <tr><th scope="col">Department</th><th scope="col">Item</th><th scope="col">KPI</th><th scope="col">Target</th><th scope="col">Actual</th><th scope="col">Achievement</th></tr>
                </thead>
                <tbody>
                  {progress.rows.map((row) => (
                    <tr key={row.item_id}>
                      <th scope="row">{department(row.vertical)}</th>
                      <td style={{ overflowWrap: "anywhere" }}>{row.text}</td>
                      <td>{row.kpi_label}</td>
                      <td>{formatTarget(row.target, row.unit)}</td>
                      <td>{formatTarget(row.actual, row.unit)}</td>
                      <td><span className={achievementClass(row.achievement)}>{formatAchievement(row.achievement)}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {progress.free_text.total > 0 && <p style={{ marginBottom: 0 }}>Other plan items: {progress.free_text.done} of {progress.free_text.total} done.</p>}
        </>
      )}
    </section>
  );
}
