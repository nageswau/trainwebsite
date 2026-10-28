import Link from "next/link";

import IntakeFilter from "@/components/IntakeFilter";
import { LEAD_DIVISIONS, PERFORMANCE_HOME, type CounselorPerformanceReport, type PerformanceFigure, type PerformanceQuery } from "@/lib/counselorPerformance";
import { formatCalendarDate } from "@/lib/formatDate";
import { formatCount, formatPct } from "@/lib/managementCounseling";

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

// ccrm-053 (PF2, PF3): the period, intake and lead-division form -- a GET form, so refresh, back and shared links keep every filter.
// `period` is what the API answered (its default month), else the address.
export function PerformanceFilters({ home, query, period }: { home: string; query: PerformanceQuery; period: { from: string; to: string } }) {
  return (
    <form key={`${period.from}-${period.to}-${query.intake}-${query.division}`} method="get" action={home} aria-label="Choose a period" className="analytics-form" autoComplete="off">
      <div className="field" style={{ margin: 0 }}>
        <label htmlFor="performance-from">From</label>
        <input id="performance-from" className="input" type="date" name="from" defaultValue={period.from} required />
      </div>
      <div className="field" style={{ margin: 0 }}>
        <label htmlFor="performance-to">To</label>
        <input id="performance-to" className="input" type="date" name="to" defaultValue={period.to} required />
      </div>
      <IntakeFilter id="performance-intake" name="intake" defaultValue={query.intake} />
      <div className="field" style={{ margin: 0 }}>
        <label htmlFor="performance-division">Lead division</label>
        <select id="performance-division" name="division" defaultValue={query.division}>
          <option value="">All divisions</option>
          {LEAD_DIVISIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </div>
      <button className="btn" type="submit">Show</button>
      <Link className="btn secondary" href={home}>This month</Link>
    </form>
  );
}

// ccrm-036 (DEC-SCOPE-269, P2-P8): the filter form, the period's figures, the figures now, and the caseload by stage and sub-status.
// Server-rendered. ccrm-053: `home` is the page the form submits to -- the counselor's own, or the Overseas Admin's read of one counselor
// (`data.counselor`), whose name then replaces "you".
export default function CounselorPerformance({ data, error, query, home = PERFORMANCE_HOME }: { data: CounselorPerformanceReport | null; error: string; query: PerformanceQuery; home?: string }) {
  const period = { from: data?.from ?? query.from, to: data?.to ?? query.to };
  const whose = data?.counselor ? `${data.counselor.full_name}’s` : "Your";
  return (
    <div className="action-card">
      {error && <p className="form-error" role="alert">{error}</p>}
      <PerformanceFilters home={home} query={query} period={period} />
      {data && (
        <>
          <section>
            <h3>In the period</h3>
            <p className="muted">
              {formatCalendarDate(data.from)} to {formatCalendarDate(data.to)}, India time (IST). Counted the same way as the management counseling dashboard.
              {(data.intake || data.division) && ` Leads${data.intake ? ` for the ${data.intake} intake` : ""}${data.division ? ` in the ${data.division === "it" ? "IT" : "Overseas"} division` : ""} only.`}
            </p>
            <Tiles label="In the period" figures={data.period} />
          </section>
          <section>
            <h3>Now</h3>
            <p className="muted">
              {whose} tasks, follow-ups and applications as they stand today, whatever the period.{data.intake && ` Applications for the ${data.intake} intake only.`}
            </p>
            <Tiles label="Now" figures={data.now} />
          </section>
          <section>
            <h3 id="applications-heading">Applications by stage and sub-status</h3>
            {data.applications.rows.length === 0 ? (
              <p className="empty" role="status">{data.counselor ? `No applications are assigned to ${data.counselor.full_name}` : "No applications are assigned to you"}{data.intake ? ` for the ${data.intake} intake` : ""} yet.</p>
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
