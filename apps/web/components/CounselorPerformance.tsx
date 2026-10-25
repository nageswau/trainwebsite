import Link from "next/link";

import { PERFORMANCE_HOME, type CounselorPerformanceReport, type PerformanceFigure } from "@/lib/counselorPerformance";
import { formatCalendarDate } from "@/lib/formatDate";
import { formatCount, formatPct, type CounselingQuery } from "@/lib/managementCounseling";

// A percentage with nothing to divide is said in words, never shown as 0.
const NO_SHARE: Record<string, string> = { conversion_pct: "No leads assigned", follow_up_completion_pct: "No follow-ups due" };

function Tiles({ label, figures }: { label: string; figures: PerformanceFigure[] }) {
  return (
    <ul className="metric-grid snapshot-tiles" aria-label={label}>
      {figures.map((f) => (
        <li key={f.key} className="metric">
          <span>{f.label}</span>
          {f.value === null ? (
            <strong className="metric-untracked">{NO_SHARE[f.key] ?? "—"}</strong>
          ) : (
            <strong>{f.unit === "percent" ? formatPct(f.value) : formatCount(f.value)}</strong>
          )}
          <p className="metric-note">{f.definition}</p>
        </li>
      ))}
    </ul>
  );
}

// ccrm-036 (DEC-SCOPE-269, P2-P8): the period form, the period's figures, the figures now, and the caseload by stage and sub-status.
// Server-rendered; a GET form, so refresh, back and shared links keep the period.
export default function CounselorPerformance({ data, error, query }: { data: CounselorPerformanceReport | null; error: string; query: CounselingQuery }) {
  const period = { from: data?.from ?? query.from, to: data?.to ?? query.to };
  return (
    <div className="action-card">
      {error && <p className="form-error" role="alert">{error}</p>}
      <form key={`${period.from}-${period.to}`} method="get" action={PERFORMANCE_HOME} aria-label="Choose a period" className="analytics-form" autoComplete="off">
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="performance-from">From</label>
          <input id="performance-from" className="input" type="date" name="from" defaultValue={period.from} required />
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="performance-to">To</label>
          <input id="performance-to" className="input" type="date" name="to" defaultValue={period.to} required />
        </div>
        <button className="btn" type="submit">Show</button>
        <Link className="btn secondary" href={PERFORMANCE_HOME}>This month</Link>
      </form>
      {data && (
        <>
          <section>
            <h3>In the period</h3>
            <p className="muted">{formatCalendarDate(data.from)} to {formatCalendarDate(data.to)}, India time (IST). Counted the same way as the management counseling dashboard.</p>
            <Tiles label="In the period" figures={data.period} />
          </section>
          <section>
            <h3>Now</h3>
            <p className="muted">Your tasks, follow-ups and applications as they stand today, whatever the period.</p>
            <Tiles label="Now" figures={data.now} />
          </section>
          <section>
            <h3 id="applications-heading">Applications by stage and sub-status</h3>
            {data.applications.rows.length === 0 ? (
              <p className="empty" role="status">No applications are assigned to you yet.</p>
            ) : (
              <div className="table-scroll" role="region" aria-labelledby="applications-heading" tabIndex={0}>
                <table className="table">
                  <caption className="visually-hidden">Applications by stage and sub-status</caption>
                  <thead>
                    <tr><th scope="col">Stage</th><th scope="col">Sub-status</th><th scope="col">Applications</th><th scope="col">Students</th></tr>
                  </thead>
                  <tbody>
                    {data.applications.rows.map((r) => (
                      <tr key={`${r.stage}-${r.sub_status ?? ""}`}>
                        <th scope="row">{r.stage_label}</th><td>{r.sub_status_label}</td><td>{formatCount(r.applications)}</td><td>{formatCount(r.students)}</td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr>
                      <th scope="row">Total</th><td />
                      <td><strong>{formatCount(data.applications.total.applications)}</strong></td><td><strong>{formatCount(data.applications.total.students)}</strong></td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            )}
            <dl className="metric-note">
              {data.applications.definitions.map((d) => (
                <div key={d.key}><dt style={{ display: "inline", fontWeight: 700 }}>{d.label}: </dt><dd style={{ display: "inline", margin: 0 }}>{d.definition}</dd></div>
              ))}
            </dl>
          </section>
        </>
      )}
    </div>
  );
}
