import Link from "next/link";

import { formatCalendarDate } from "@/lib/formatDate";
import { formatCount, formatPct } from "@/lib/managementCounseling";
import { TRAINING_HOME, type TrainerFigureKey, type TrainerRow, type TrainingDashboard, type TrainingKpi, type TrainingQuery } from "@/lib/managementTraining";

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;
// TR8/TR9: a share with nothing to divide says why, never 0.
const NO_SHARE: Partial<Record<TrainingKpi["key"], string>> = { attendance_pct: "Nothing marked", completion_pct: "No seats taken" };

function KpiValue({ kpi }: { kpi: TrainingKpi }) {
  if (kpi.value === null) return <strong className="metric-untracked">{NO_SHARE[kpi.key] ?? "—"}</strong>;
  return <strong>{kpi.key.endsWith("_pct") ? formatPct(kpi.value) : formatCount(kpi.value)}</strong>;
}

function cell(key: TrainerFigureKey, row: TrainerRow): string {
  const value = row[key];
  if (value === null) return "—";
  if (key === "feedback_avg") return `${value.toFixed(1)} / 5 (${formatCount(row.feedback_count)})`;
  if (key === "students_trained" || key === "placements") return formatCount(value);
  return formatPct(value);
}

// mgmt-017 (EVID-017 §12, spec TR1-TR16): the period form, the 11 Training KPIs (company-wide) and the trainer table with the 7 trainer
// metrics. Server-rendered; a GET form, so refresh, back and shared links keep the period.
export default function ManagementTraining({ data, error, query }: { data: TrainingDashboard | null; error: string; query: TrainingQuery }) {
  const period = { from: data?.from ?? query.from, to: data?.to ?? query.to };
  const inactive = data?.trainers.filter((t) => !t.active).length ?? 0;
  return (
    <div className="action-card">
      {error && <p className="form-error" role="alert">{error}</p>}
      <form key={`${period.from}-${period.to}`} method="get" action={TRAINING_HOME} aria-label="Choose a period" className="analytics-form" autoComplete="off">
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="training-from">From</label>
          <input id="training-from" className="input" type="date" name="from" defaultValue={period.from} required />
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="training-to">To</label>
          <input id="training-to" className="input" type="date" name="to" defaultValue={period.to} required />
        </div>
        <button className="btn" type="submit">Show</button>
        <Link className="btn secondary" href={TRAINING_HOME}>This month</Link>
      </form>
      {data && (
        <>
          <p className="muted">
            {formatCalendarDate(data.from)} to {formatCalendarDate(data.to)}, India time (IST). {plural(data.trainers.length, "trainer account")}
            {inactive > 0 && `, ${inactive} inactive`}. Every figure is counted live from the EduSphere records.
          </p>
          <section>
            <h3>Training KPIs</h3>
            <ul className="metric-grid snapshot-tiles" aria-label="Training KPIs">
              {data.kpis.map((kpi) => (
                <li key={kpi.key} className="metric">
                  <span>{kpi.label}</span>
                  <KpiValue kpi={kpi} />
                  <p className="metric-note">{kpi.definition}</p>
                </li>
              ))}
            </ul>
          </section>
          <section id="trainers">
            <h3 id="trainers-heading">Trainer performance</h3>
            {data.trainers.length === 0 ? (
              <p className="empty" role="status">No trainer accounts yet.</p>
            ) : (
              <div className="table-scroll" role="region" aria-labelledby="trainers-heading" tabIndex={0}>
                <table className="table">
                  <caption className="visually-hidden">Trainer performance</caption>
                  <thead>
                    <tr>
                      <th scope="col">Trainer</th><th scope="col">Batches</th>
                      {data.trainer_figures.map((f) => <th key={f.key} scope="col">{f.label}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {data.trainers.map((t) => (
                      <tr key={t.id}>
                        <th scope="row">{t.full_name}{!t.active && <span className="muted"> · Inactive</span>}</th>
                        <td>{formatCount(t.batches)}</td>
                        {data.trainer_figures.map((f) => <td key={f.key}>{cell(f.key, t)}</td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <ul className="muted" aria-label="What the trainer figures mean">
              {data.trainer_figures.map((f) => <li key={f.key}><strong>{f.label}:</strong> {f.definition}</li>)}
            </ul>
            <p className="muted">A batch counts for the trainer assigned to it. The KPIs above are company-wide, so they are not the sum of the rows.</p>
          </section>
        </>
      )}
    </div>
  );
}
