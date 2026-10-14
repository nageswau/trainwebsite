import Link from "next/link";

import { amountsText } from "@/lib/commissionLedger";
import { formatCalendarDate } from "@/lib/formatDate";
import { PERIOD_KPIS, UNIVERSITIES_HOME, universitiesHref, type UniversitiesDashboard, type UniversitiesQuery } from "@/lib/managementUniversities";
import { weightedText } from "@/lib/partnershipExpected";

const count = (value: number) => value.toLocaleString("en-IN");

// mgmt-023 (EVID-017 §19, spec UD1-UD14): the University partnership dashboard for the operational tier. Server-rendered; the period is
// a GET form. Every figure is the University Partnership CRM's own (upc-018/019/023/029), so the totals equal its global dashboard. The
// Revenue tile exists only when the API sends `revenue` (partners, M3); super_admin never receives it (M13).
export default function ManagementUniversities({ data, error, query }: { data: UniversitiesDashboard | null; error: string; query: UniversitiesQuery }) {
  const shown = data?.expected.next_month;
  return (
    <>
      {error && <p className="form-error" role="alert">{error}</p>}
      {/* Keyed on the address so a client navigation (This month, Back) remounts the uncontrolled inputs; with no dates in the address
          the inputs show the period the API used. */}
      <form key={universitiesHref(query)} method="get" action={UNIVERSITIES_HOME} aria-label="Universities period" className="funnel-filters" autoComplete="off">
        <div className="field">
          <label htmlFor="universities-from">From</label>
          <input id="universities-from" name="from" type="date" defaultValue={query.from || data?.from} />
        </div>
        <div className="field">
          <label htmlFor="universities-to">To</label>
          <input id="universities-to" name="to" type="date" defaultValue={query.to || data?.to} />
        </div>
        <div className="funnel-filter-actions">
          <button className="btn" type="submit">Apply</button>
          {(query.from || query.to) && <Link href={UNIVERSITIES_HOME}>This month</Link>}
        </div>
      </form>
      {data && shown && (
        <>
          <p className="muted">
            Partnership figures are as of {formatCalendarDate(data.today)}. Applications, Enrollments{data.revenue ? " and Revenue" : ""} cover{" "}
            {formatCalendarDate(data.from)} to {formatCalendarDate(data.to)} (India time). Contacted to Signed count the universities at or past
            that step today; lost / closed universities count only as identified.
          </p>
          <ul className="metric-grid snapshot-tiles university-tiles" aria-label="University partnership KPIs">
            {data.kpis.map((kpi) => (
              <li key={kpi.key} className="metric">
                <span>{kpi.label}</span>
                <strong>{count(kpi.value)}</strong>
                {PERIOD_KPIS.has(kpi.key) && <small className="muted">In the period</small>}
              </li>
            ))}
            {data.revenue && (
              <li className="metric">
                <span>Revenue</span>
                <strong className="metric-money">{amountsText(data.revenue.received)}</strong>
                <small className="muted">Commission received · Expected {amountsText(data.revenue.expected)}</small>
              </li>
            )}
          </ul>
          <section className="card" aria-labelledby="universities-pipeline">
            <h3 id="universities-pipeline">Partnership pipeline</h3>
            <p className="muted">Where each university stands today, by the stage it is in now.</p>
            <ol className="funnel" aria-label="Partnership pipeline">
              {data.pipeline.steps.map((step) => (
                <li className="funnel-row" key={step.key}>
                  <span className="funnel-label">{step.label}</span>
                  <span className="funnel-count">{count(step.count)}</span>
                </li>
              ))}
            </ol>
            {data.pipeline.lost > 0 && (
              <p className="muted">
                {count(data.pipeline.lost)} lost / closed are not in a step; {count(data.pipeline.total)} universities in all.
              </p>
            )}
          </section>
          <section aria-labelledby="universities-expected" className="universities-expected">
            <h3 id="universities-expected" className="telecalling-section-title">Expected Partnership Date</h3>
            <ul className="metric-grid snapshot-tiles university-tiles" aria-label="Expected partnerships">
              {data.expected.windows.map((w) => (
                <li key={w.key} className="metric">
                  <span>{w.label}</span>
                  <strong>{count(w.count)}</strong>
                  <small className="muted">Weighted {weightedText(w.weighted)}</small>
                </li>
              ))}
            </ul>
            {data.expected.undated > 0 && <p className="muted">{count(data.expected.undated)} in progress have no expected date.</p>}
            <h4 id="universities-next-month">Expected to sign next month</h4>
            {shown.total === 0 ? (
              <p className="empty" role="status">No universities are expected to sign next month.</p>
            ) : (
              <>
                <div className="table-wrap" role="region" aria-labelledby="universities-next-month" tabIndex={0} style={{ overflowX: "auto" }}>
                  <table className="table" style={{ minWidth: 720 }}>
                    <caption className="visually-hidden">Universities expected to sign next month</caption>
                    <thead>
                      <tr>
                        <th scope="col">University</th>
                        <th scope="col">Country</th>
                        <th scope="col">Stage</th>
                        <th scope="col">Expected date</th>
                        <th scope="col">Owner</th>
                        <th scope="col">Probability</th>
                      </tr>
                    </thead>
                    <tbody>
                      {shown.items.map((row) => (
                        <tr key={row.university.id}>
                          <th scope="row">{row.university.name}</th>
                          <td>{row.country}</td>
                          <td>{row.stage_label}</td>
                          <td className="no-wrap">{formatCalendarDate(row.expected_agreement_date)}</td>
                          <td>{row.owner?.full_name ?? "Not assigned"}</td>
                          <td>{row.probability}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {shown.total > shown.items.length && (
                  <p className="muted">
                    Showing {shown.items.length} of {shown.total}, earliest expected date first.
                  </p>
                )}
              </>
            )}
          </section>
        </>
      )}
    </>
  );
}
