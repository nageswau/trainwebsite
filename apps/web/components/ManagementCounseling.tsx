import Link from "next/link";

import { formatCalendarDate } from "@/lib/formatDate";
import {
  COUNSELING_HOME, formatCount, formatPct, type CounselingDashboard, type CounselingFigureKey, type CounselingFigures, type CounselingQuery,
} from "@/lib/managementCounseling"; // prettier-ignore
import { formatInr } from "@/lib/managementLedger";

const COLUMNS: CounselingFigureKey[] = ["leads_assigned", "counseling_sessions", "follow_ups", "conversions", "revenue", "conversion_pct"];
const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;

/** A tile's value: words, not a 0, where there is no figure to show (CS4, CS8, CS9). */
function TileValue({ figure, values }: { figure: CounselingFigureKey; values: CounselingFigures }) {
  const value = values[figure];
  if (figure === "calls") return <strong className="metric-untracked">Not tracked</strong>;
  if (figure === "revenue" && value === null) return <strong className="metric-untracked">Partners only</strong>;
  if (figure === "conversion_pct" && value === null) return <strong className="metric-untracked">No leads assigned</strong>;
  return <strong>{cell(figure, values)}</strong>;
}

function cell(figure: CounselingFigureKey, values: CounselingFigures): string {
  const value = values[figure];
  if (value === null) return "—";
  if (figure === "revenue") return formatInr(value as string);
  if (figure === "conversion_pct") return formatPct(value as number);
  return formatCount(value as number);
}

// mgmt-018 (EVID-017 §13, spec CS1-CS12): the period form, the totals as the §13 KPIs (Leads → Counseling → Conversion), and the
// counselor-wise table with division and all-counselor totals. Server-rendered; a GET form, so refresh, back and shared links keep it.
export default function ManagementCounseling({ data, error, query }: { data: CounselingDashboard | null; error: string; query: CounselingQuery }) {
  const period = { from: data?.from ?? query.from, to: data?.to ?? query.to };
  const columns = data ? COLUMNS.filter((key) => key !== "revenue" || data.revenue_visible) : [];
  const label = (key: CounselingFigureKey) => data?.figures.find((f) => f.key === key)?.label ?? key;
  return (
    <div className="action-card">
      {error && <p className="form-error" role="alert">{error}</p>}
      <form key={`${period.from}-${period.to}`} method="get" action={COUNSELING_HOME} aria-label="Choose a period" className="analytics-form" autoComplete="off">
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="counseling-from">From</label>
          <input id="counseling-from" className="input" type="date" name="from" defaultValue={period.from} required />
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="counseling-to">To</label>
          <input id="counseling-to" className="input" type="date" name="to" defaultValue={period.to} required />
        </div>
        <button className="btn" type="submit">Show</button>
        <Link className="btn secondary" href={COUNSELING_HOME}>This month</Link>
      </form>
      {data && (
        <>
          <p className="muted">
            {formatCalendarDate(data.from)} to {formatCalendarDate(data.to)}, India time (IST). {plural(data.total.counselor_count, "counselor")}. Every figure is
            counted live from the EduSphere records.
          </p>
          <section>
            <h3>Leads → Counseling → Conversion</h3>
            <ul className="metric-grid snapshot-tiles" aria-label="Leads → Counseling → Conversion">
              {data.figures.map((f) => (
                <li key={f.key} className="metric">
                  <span>{f.label}</span>
                  <TileValue figure={f.key} values={data.total} />
                  <p className="metric-note">{f.definition}</p>
                </li>
              ))}
            </ul>
          </section>
          <section id="counselors">
            <h3 id="counselors-heading">Counselor-wise performance</h3>
            {data.counselors.length === 0 ? (
              <p className="empty" role="status">No counselor accounts yet.</p>
            ) : (
              <div className="table-scroll" role="region" aria-labelledby="counselors-heading" tabIndex={0}>
                <table className="table">
                  <caption className="visually-hidden">Counselor-wise performance</caption>
                  <thead>
                    <tr>
                      <th scope="col">Counselor</th><th scope="col">Division</th>
                      {columns.map((key) => <th key={key} scope="col">{label(key)}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {data.counselors.map((c) => (
                      <tr key={c.id}>
                        <th scope="row">{c.full_name}{!c.active && <span className="muted"> · Inactive</span>}</th>
                        <td>{data.divisions.find((g) => g.division === c.division)?.label ?? c.division}</td>
                        {columns.map((key) => <td key={key}>{cell(key, c)}</td>)}
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    {[...data.divisions.filter((g) => g.counselor_count > 0), data.total].map((g) => (
                      <tr key={g.division ?? "all"}>
                        <th scope="row">{g.division === null ? g.label : `${g.label} total`}</th>
                        <td className="no-wrap">{plural(g.counselor_count, "counselor")}</td>
                        {columns.map((key) => <td key={key}><strong>{cell(key, g)}</strong></td>)}
                      </tr>
                    ))}
                  </tfoot>
                </table>
              </div>
            )}
            <p className="muted">Calls are not tracked for counselors: telecallers log calls in EduSphere.</p>
          </section>
        </>
      )}
    </div>
  );
}
