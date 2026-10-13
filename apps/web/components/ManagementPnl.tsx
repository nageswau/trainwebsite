import { formatCalendarDate } from "@/lib/formatDate";
import { formatMonth } from "@/lib/managementExpenses";
import { formatInr, formatMoney } from "@/lib/managementLedger";
import { PNL_HOME, formatMargin, isLoss, type Pnl, type PnlFigures, type PnlQuery } from "@/lib/managementPnl";

const TITLE = "Profit and loss by business vertical";

/** PL9: a negative contribution in red; the minus sign stays, so colour is never the only cue. */
function lossClass(amount: string): string | undefined {
  return isLoss(amount) ? "pnl-loss" : undefined;
}

function Cells({ figures }: { figures: PnlFigures }) {
  return (
    <>
      <td>{formatInr(figures.revenue)}</td>
      <td>{formatInr(figures.expenses)}</td>
      <td><span className={lossClass(figures.contribution)}>{formatInr(figures.contribution)}</span></td>
      <td>{formatMargin(figures.margin)}</td>
    </>
  );
}

// mgmt-009 (EVID-017 §7, spec PL1-PL12): "which business is actually making money" -- the company's revenue, expenses, net profit and
// margin, then one P&L row per vertical, the unallocated shared costs and the total (the rows' sum). Server-rendered; the period is a
// GET form, so refresh, back and shared links keep it.
export default function ManagementPnl({ data, error, query, maxMonth }: { data: Pnl | null; error: string; query: PnlQuery; maxMonth: string }) {
  const range = { month: data?.month ?? query.month, period: data?.period ?? query.period };
  const empty = data && Number(data.total.revenue) === 0 && Number(data.total.expenses) === 0;
  return (
    <div className="action-card">
      {error && <p className="form-error" role="alert">{error}</p>}
      <form key={`${range.month}-${range.period}`} method="get" action={PNL_HOME} aria-label="Choose a period" className="analytics-form" autoComplete="off">
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="pnl-month">Month</label>
          <input id="pnl-month" className="input" type="month" name="month" defaultValue={range.month} max={maxMonth} min="2000-01" />
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="pnl-period">Show</label>
          <select id="pnl-period" className="input" name="period" defaultValue={range.period}>
            <option value="month">That month</option>
            <option value="quarter">Quarter to date</option>
            <option value="year">Financial year to date</option>
          </select>
        </div>
        <button className="btn" type="submit">Show</button>
      </form>
      {data && (
        <>
          <p className="muted">
            {data.label}: {formatCalendarDate(data.start)} to {formatCalendarDate(data.end)}. Approved ledger entries and automatic lines, in rupees.
            Company-wide shared costs (rent, salaries) are not split across the verticals; they are their own row.
          </p>
          {!data.commission_visible && <p className="muted">University commission is not included: only partners see it.</p>}
          {data.not_counted.length > 0 && (
            <p className="muted" style={{ fontSize: 13 }}>
              Automatic lines in another currency are not counted:{" "}
              {data.not_counted.map((n) => `${formatMoney(n.amount, n.currency)} ${n.kind} (${n.count} ${n.count === 1 ? "line" : "lines"})`).join(", ")}.
            </p>
          )}
          <ul className="metric-grid snapshot-tiles money-tiles accounts-tiles" aria-label="Company figures">
            <li className="metric"><span>Revenue</span><strong>{formatInr(data.total.revenue)}</strong></li>
            <li className="metric"><span>Expenses</span><strong>{formatInr(data.total.expenses)}</strong></li>
            <li className="metric"><span>Net profit</span><strong className={lossClass(data.total.contribution)}>{formatInr(data.total.contribution)}</strong></li>
            <li className="metric"><span>Margin</span><strong>{formatMargin(data.total.margin)}</strong></li>
          </ul>
          {empty && (
            <p className="empty" role="status">No revenue or expenses recorded in {data.period === "month" ? formatMonth(data.month) : `the ${data.label.toLowerCase()}`}.</p>
          )}
          <h3 id="pnl-verticals">Business vertical P&amp;L</h3>
          <div className="table-wrap" role="region" aria-labelledby="pnl-verticals" tabIndex={0} style={{ overflowX: "auto" }}>
            <table className="table pnl-table">
              <caption className="visually-hidden">{TITLE}</caption>
              <thead>
                <tr><th scope="col">Vertical</th><th scope="col">Revenue</th><th scope="col">Expenses</th><th scope="col">Contribution</th><th scope="col">Margin</th></tr>
              </thead>
              <tbody>
                {data.rows.map((row) => (
                  <tr key={row.key}>
                    <th scope="row">{row.label}</th>
                    <Cells figures={row} />
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <th scope="row">Total</th>
                  <Cells figures={data.total} />
                </tr>
              </tfoot>
            </table>
          </div>
          <p className="muted">Contribution = revenue − expenses. Margin = contribution as a share of revenue; “—” when there is no revenue.</p>
        </>
      )}
    </div>
  );
}
