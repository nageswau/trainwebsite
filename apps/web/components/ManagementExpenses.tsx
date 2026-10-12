import Link from "next/link";

import { formatCalendarDate } from "@/lib/formatDate";
import { EXPENSES_HOME, expensesLedgerHref, formatMonth, type ExpenseDashboard } from "@/lib/managementExpenses";
import { formatInr, formatMoney } from "@/lib/managementLedger";

// mgmt-010 (EVID-017 §8, spec ME1-ME8): the §8 table -- each head's monthly and annual (financial year to date) figure with a bar of
// its share of the year, the total, then the categories behind the heads and the months that add up to the year. Server-rendered;
// the month is a GET form, so refresh, back and shared links keep it.
export default function ManagementExpenses({ data, error, month, maxMonth }: { data: ExpenseDashboard | null; error: string; month: string; maxMonth: string }) {
  const heads = new Map(data?.groups.map((g) => [g.key, g.label]));
  return (
    <div className="action-card">
      {error && <p className="form-error" role="alert">{error}</p>}
      <form method="get" action={EXPENSES_HOME} aria-label="Expense month" className="analytics-form" autoComplete="off">
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="expense-month">Month</label>
          <input id="expense-month" className="input" type="month" name="month" defaultValue={data?.month ?? month} max={maxMonth} min="2000-01" />
        </div>
        <button className="btn" type="submit">Show</button>
      </form>
      {data && (
        <>
          <p className="muted">
            Monthly: {formatMonth(data.month)}. Annual: the financial year {data.year_label} to date, from {formatCalendarDate(data.year_start)}. Approved
            manual expenses and automatic expense lines, in rupees.
          </p>
          {data.not_counted.length > 0 && (
            <p className="muted" style={{ fontSize: 13 }}>
              Automatic expenses in another currency are not counted: {data.not_counted.map((n) => `${formatMoney(n.amount, n.currency)} (${n.count} ${n.count === 1 ? "line" : "lines"})`).join(", ")}.
            </p>
          )}
          {Number(data.totals.year) === 0 && (
            <p className="empty" role="status">No expenses are recorded in the financial year {data.year_label} up to {formatMonth(data.month)} yet.</p>
          )}
          <div className="table-wrap" role="region" aria-label="Expenses by head" tabIndex={0} style={{ overflowX: "auto" }}>
            <table className="table" style={{ minWidth: 560 }}>
              <caption className="visually-hidden">Expenses by head</caption>
              <thead>
                <tr><th scope="col">Expense</th><th scope="col">Monthly</th><th scope="col">Annual</th><th scope="col">Share of year</th></tr>
              </thead>
              <tbody>
                {data.groups.map((g) => (
                  <tr key={g.key}>
                    <th scope="row">{g.label}</th>
                    <td>{formatInr(g.month)}</td>
                    <td>{formatInr(g.year)}</td>
                    <td>
                      <span className="expense-share">
                        <span className="expense-bar" aria-hidden="true"><span style={{ width: `${g.share}%` }} /></span>
                        {g.share}%
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr><th scope="row">Total</th><td><strong>{formatInr(data.totals.month)}</strong></td><td><strong>{formatInr(data.totals.year)}</strong></td><td /></tr>
              </tfoot>
            </table>
          </div>
          {data.categories.length > 0 && (
            <div className="table-wrap" role="region" aria-label="By category" tabIndex={0} style={{ overflowX: "auto" }}>
              <table className="table" style={{ minWidth: 560 }}>
                <caption>By category</caption>
                <thead>
                  <tr><th scope="col">Category</th><th scope="col">Head</th><th scope="col">Monthly</th><th scope="col">Annual</th></tr>
                </thead>
                <tbody>
                  {data.categories.map((c) => (
                    <tr key={c.label}><th scope="row">{c.label}</th><td>{heads.get(c.group) ?? c.group}</td><td>{formatInr(c.month)}</td><td>{formatInr(c.year)}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="table-wrap" role="region" aria-label="Month by month" tabIndex={0} style={{ overflowX: "auto" }}>
            <table className="table">
              <caption>Month by month</caption>
              <thead>
                <tr><th scope="col">Month</th><th scope="col">Expenses</th></tr>
              </thead>
              <tbody>
                {data.months.map((m) => (
                  <tr key={m.month}><th scope="row">{formatMonth(m.month)}</th><td>{formatInr(m.total)}</td></tr>
                ))}
              </tbody>
              <tfoot>
                <tr><th scope="row">Financial year to date</th><td><strong>{formatInr(data.totals.year)}</strong></td></tr>
              </tfoot>
            </table>
          </div>
          <p>
            <Link className="kpi-link" href={expensesLedgerHref(data.month)}>Open {formatMonth(data.month)}&apos;s expense lines in the ledger</Link>
          </p>
        </>
      )}
    </div>
  );
}
