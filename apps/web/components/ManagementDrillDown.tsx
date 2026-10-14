import Link from "next/link";

import { formatCalendarDate } from "@/lib/formatDate";
import { DRILL_HOME, DRILL_LABEL, drillHref, type Drill, type DrillChain, type DrillQuery, type DrillRecord } from "@/lib/managementDrill";
import { formatInr, formatMoney } from "@/lib/managementLedger";

const AUDITED_LEVELS = new Set(["student", "application", "payment"]); // DD11: the server records these reads

// mgmt-033 (EVID-017 "the key difference", spec DD1-DD14): one level of a revenue chain -- the path so far as breadcrumbs, the figure it
// drills into, and the next level's rows (each a link one level down, the unattributed row too), or the transaction record read-only at
// the end. Server-rendered; the period and the path live in the address, so refresh, back and shared links keep them.
export default function ManagementDrillDown({ chain, data, error, query, maxMonth }: { chain: DrillChain; data: Drill | null; error: string; query: DrillQuery; maxMonth: string }) {
  const range = { month: data?.month ?? query.month, period: data?.period ?? query.period };
  const path = data ? data.breadcrumbs.map((crumb) => crumb.key) : query.path;
  return (
    <div className="action-card">
      <form key={`${range.month}-${range.period}-${path.join(",")}`} method="get" action={`${DRILL_HOME}/${chain}`} aria-label="Choose a period" className="analytics-form" autoComplete="off">
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="drill-month">Month</label>
          <input id="drill-month" className="input" type="month" name="month" defaultValue={range.month} max={maxMonth} min="2000-01" />
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="drill-period">Show</label>
          <select id="drill-period" className="input" name="period" defaultValue={range.period}>
            <option value="month">That month</option>
            <option value="year">Financial year to date</option>
          </select>
        </div>
        {path.length > 0 && <input type="hidden" name="path" value={path.join(",")} />}
        <button className="btn" type="submit">Show</button>
      </form>
      {error && (
        <>
          <p className="form-error" role="alert">{error}</p>
          <p><Link className="kpi-link" href={drillHref(chain, range, [])}>Start again from the top</Link></p>
        </>
      )}
      {data && <Level chain={chain} data={data} page={query.page} />}
    </div>
  );
}

function Level({ chain, data, page }: { chain: DrillChain; data: Drill; page: number }) {
  const range = { month: data.month, period: data.period };
  const path = data.breadcrumbs.map((crumb) => crumb.key);
  const audited = data.record !== null || (data.level !== null && AUDITED_LEVELS.has(data.level.key));
  return (
    <>
      <nav aria-label="Drill-down path" className="drill-path">
        <ol>
          <li>
            {path.length ? <Link href={drillHref(chain, range, [])}>{data.chain_label}</Link> : <span aria-current="page">{data.chain_label}</span>}
          </li>
          {data.breadcrumbs.map((crumb, i) => (
            <li key={`${crumb.level}-${crumb.key}`}>
              <span className="muted">{crumb.level_label}: </span>
              {i === path.length - 1 ? <span aria-current="page">{crumb.name}</span> : <Link href={drillHref(chain, range, path.slice(0, i + 1))}>{crumb.name}</Link>}
            </li>
          ))}
        </ol>
      </nav>
      <p className="muted">
        {data.label}: {formatCalendarDate(data.start)} to {formatCalendarDate(data.end)}. Counted income in rupees, the same lines as the {DRILL_LABEL[chain]} dashboard.
      </p>
      <ul className="metric-grid snapshot-tiles money-tiles" aria-label="Drill-down figures">
        <li className="metric"><span>{data.breadcrumbs.at(-1)?.name ?? data.chain_label}</span><strong>{formatInr(data.total)}</strong></li>
        <li className="metric"><span>Lines</span><strong>{data.count}</strong></li>
      </ul>
      {data.record ? <Record record={data.record} /> : data.level && data.rows.length === 0 ? (
        <p className="empty" role="status">No counted {data.chain_label} in {data.period === "year" ? `the ${data.label.toLowerCase()}` : data.label}.</p>
      ) : data.level && (
        <>
          <h3 id="drill-level">By {data.level.label.toLowerCase()}</h3>
          <div className="table-wrap" role="region" aria-labelledby="drill-level" tabIndex={0} style={{ overflowX: "auto" }}>
            <table className="table" style={{ minWidth: 480 }}>
              <caption className="visually-hidden">By {data.level.label.toLowerCase()}</caption>
              <thead>
                <tr><th scope="col">{data.level.label}</th><th scope="col">Lines</th><th scope="col">Latest</th><th scope="col">Amount</th></tr>
              </thead>
              <tbody>
                {data.rows.map((row) => (
                  <tr key={row.key}>
                    <th scope="row"><Link href={drillHref(chain, range, [...path, row.key])}>{row.name}</Link></th>
                    <td>{row.count}</td>
                    <td>{formatCalendarDate(row.latest)}</td>
                    <td>{formatInr(row.amount)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr><th scope="row">Total</th><td>{data.count}</td><td /><td><strong>{formatInr(data.total)}</strong></td></tr>
              </tfoot>
            </table>
          </div>
          {data.total_rows > data.rows.length && (
            <>
              <p className="muted" role="status">Showing {data.offset + 1}–{data.offset + data.rows.length} of {data.total_rows}.</p>
              <nav aria-label="Drill-down pages" style={{ display: "flex", gap: 12 }}>
                {page > 1 && <Link className="btn secondary" href={drillHref(chain, range, path, page - 1)}>Previous</Link>}
                {data.offset + data.rows.length < data.total_rows && <Link className="btn secondary" href={drillHref(chain, range, path, page + 1)}>Next</Link>}
              </nav>
            </>
          )}
        </>
      )}
      {audited && <p className="muted" style={{ fontSize: 13 }}>Names only. Opening individual students and payments is recorded in Management activity.</p>}
    </>
  );
}

function Record({ record }: { record: DrillRecord }) {
  return (
    <section aria-labelledby="drill-record" className="drill-record">
      <h3 id="drill-record">Payment record</h3>
      <dl>
        <dt>Date</dt><dd>{formatCalendarDate(record.entry_date)}</dd>
        <dt>Amount</dt><dd><strong>{formatMoney(record.amount, record.currency)}</strong></dd>
        <dt>Description</dt><dd>{record.description}</dd>
        {record.details.map((detail) => (
          <div key={detail.label} style={{ display: "contents" }}><dt>{detail.label}</dt><dd>{detail.value}</dd></div>
        ))}
      </dl>
      {record.outcomes && (
        <>
          <h4 id="drill-outcomes">{record.outcomes.title}</h4>
          {record.outcomes.items.length ? (
            <ul aria-labelledby="drill-outcomes">
              {record.outcomes.items.map((item) => (
                <li key={`${item.name}-${item.status}`}>{item.name}{item.detail ? ` (${item.detail})` : ""} — {item.status}</li>
              ))}
            </ul>
          ) : (
            <p className="muted">None recorded.</p>
          )}
        </>
      )}
    </section>
  );
}
