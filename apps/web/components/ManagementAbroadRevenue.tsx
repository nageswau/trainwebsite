import Link from "next/link";

import { formatCalendarDate } from "@/lib/formatDate";
import { ABROAD_REVENUE_HOME, abroadLedgerHref, revenueShare, type AbroadRevenue, type AbroadRevenueRow, type MonthYear } from "@/lib/managementAbroadRevenue";
import { formatMonth } from "@/lib/managementExpenses";
import { formatInr, formatMoney } from "@/lib/managementLedger";

const ROW_HEADER: Record<string, string> = { country: "Country", university: "University", intake: "Intake", agency: "Agency" };

/** A titled table in its own scroll region; the title sits outside the scroll area, so a phone sees it whole (mgmt-010 QA-02). */
function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <>
      <h3 id={id}>{title}</h3>
      <div className="table-wrap" role="region" aria-labelledby={id} tabIndex={0} style={{ overflowX: "auto" }}>
        {children}
      </div>
    </>
  );
}

function Figures({ figure }: { figure: MonthYear }) {
  return (
    <>
      <td>{formatInr(figure.month)}</td>
      <td>{formatInr(figure.year)}</td>
    </>
  );
}

function Share({ amount, total }: { amount: string; total: string }) {
  const share = revenueShare(amount, total);
  return (
    <td>
      <span className="expense-share">
        <span className="expense-bar" aria-hidden="true"><span style={{ width: `${share}%` }} /></span>
        {share}%
      </span>
    </td>
  );
}

// mgmt-006 (EVID-017 §4, spec MR1-MR12): Abroad Education revenue, expenses and gross contribution for the month and the financial year
// to date; revenue by kind; the country / university / intake / agency breakdowns, each with its Unattributed row and a bar of its share
// of the year; the Abroad expenses. Server-rendered; the month is a GET form, so refresh, back and shared links keep it.
export default function ManagementAbroadRevenue({ data, error, month, maxMonth }: { data: AbroadRevenue | null; error: string; month: string; maxMonth: string }) {
  return (
    <div className="action-card">
      {error && <p className="form-error" role="alert">{error}</p>}
      <form method="get" action={ABROAD_REVENUE_HOME} aria-label="Revenue month" className="analytics-form" autoComplete="off">
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="abroad-month">Month</label>
          <input id="abroad-month" className="input" type="month" name="month" defaultValue={data?.month ?? month} max={maxMonth} min="2000-01" />
        </div>
        <button className="btn" type="submit">Show</button>
      </form>
      {data && <Dashboard data={data} />}
    </div>
  );
}

function Dashboard({ data }: { data: AbroadRevenue }) {
  const year = data.revenue.year;
  const rows = (items: AbroadRevenueRow[]) => items.map((r) => (
    <tr key={r.label}><th scope="row">{r.label}</th><Figures figure={r} /><Share amount={r.year} total={year} /></tr>
  )); // prettier-ignore
  return (
    <>
      <p className="muted">
        Monthly: {formatMonth(data.month)}. Annual: the financial year {data.year_label} to date, from {formatCalendarDate(data.year_start)}. Approved
        manual entries and automatic lines of the Abroad Education vertical, in rupees.
      </p>
      {!data.commission_visible && <p className="muted">University commission is shown to partners only; these figures leave it out.</p>}
      {data.not_counted.length > 0 && (
        <p className="muted" style={{ fontSize: 13 }}>
          Automatic lines in another currency are not counted: {data.not_counted.map((n) => `${formatMoney(n.amount, n.currency)} ${n.kind} (${n.count} ${n.count === 1 ? "line" : "lines"})`).join(", ")}.
        </p>
      )}
      {Number(data.revenue.year) === 0 && Number(data.expense_total.year) === 0 && (
        <p className="empty" role="status">No Abroad Education revenue or expenses are recorded in the financial year {data.year_label} up to {formatMonth(data.month)} yet.</p>
      )}
      <div className="table-wrap" role="region" aria-label="Abroad Education summary" tabIndex={0} style={{ overflowX: "auto" }}>
        <table className="table" style={{ minWidth: 420 }}>
          <caption className="visually-hidden">Abroad Education summary</caption>
          <thead>
            <tr><th scope="col">Figure</th><th scope="col">Monthly</th><th scope="col">Annual</th></tr>
          </thead>
          <tbody>
            <tr><th scope="row">Abroad Education revenue</th><Figures figure={data.revenue} /></tr>
            <tr><th scope="row">Expenses</th><Figures figure={data.expense_total} /></tr>
            <tr><th scope="row">Gross contribution</th><td><strong>{formatInr(data.contribution.month)}</strong></td><td><strong>{formatInr(data.contribution.year)}</strong></td></tr>
          </tbody>
        </table>
      </div>

      <Section id="abroad-kinds" title="Revenue by kind">
        <table className="table" style={{ minWidth: 560 }}>
          <caption className="visually-hidden">Revenue by kind</caption>
          <thead>
            <tr><th scope="col">Kind</th><th scope="col">Monthly</th><th scope="col">Annual</th><th scope="col">Share of year</th></tr>
          </thead>
          <tbody>{rows(data.kinds)}</tbody>
          <tfoot>
            <tr><th scope="row">Total revenue</th><td><strong>{formatInr(data.revenue.month)}</strong></td><td><strong>{formatInr(data.revenue.year)}</strong></td><td /></tr>
          </tfoot>
        </table>
      </Section>
      <p className="muted" style={{ fontSize: 13 }}>
        Agent-generated revenue (attributed to an agency; part of the total above): {formatInr(data.agent_generated.month)} this month, {formatInr(data.agent_generated.year)} this year.
      </p>

      {data.breakdowns.map((b) => (
        <Section key={b.key} id={`abroad-${b.key}`} title={`${b.label} revenue`}>
          <table className="table" style={{ minWidth: 560 }}>
            <caption className="visually-hidden">{b.label} revenue</caption>
            <thead>
              <tr><th scope="col">{ROW_HEADER[b.key] ?? b.label}</th><th scope="col">Monthly</th><th scope="col">Annual</th><th scope="col">Share of year</th></tr>
            </thead>
            <tbody>
              {rows(b.rows)}
              <tr><th scope="row">Unattributed</th><Figures figure={b.unattributed} /><Share amount={b.unattributed.year} total={year} /></tr>
            </tbody>
            <tfoot>
              <tr><th scope="row">Total</th><td><strong>{formatInr(data.revenue.month)}</strong></td><td><strong>{formatInr(data.revenue.year)}</strong></td><td /></tr>
            </tfoot>
          </table>
        </Section>
      ))}

      <Section id="abroad-expenses" title="Abroad expenses">
        <table className="table" style={{ minWidth: 420 }}>
          <caption className="visually-hidden">Abroad expenses</caption>
          <thead>
            <tr><th scope="col">Category</th><th scope="col">Monthly</th><th scope="col">Annual</th></tr>
          </thead>
          <tbody>
            {data.expenses.length === 0 ? (
              <tr><td colSpan={3} className="muted">No Abroad expenses in the financial year {data.year_label} to date.</td></tr>
            ) : (
              data.expenses.map((e) => <tr key={e.label}><th scope="row">{e.label}</th><Figures figure={e} /></tr>)
            )}
          </tbody>
          <tfoot>
            <tr><th scope="row">Total expenses</th><td><strong>{formatInr(data.expense_total.month)}</strong></td><td><strong>{formatInr(data.expense_total.year)}</strong></td></tr>
          </tfoot>
        </table>
      </Section>
      <p className="muted" style={{ fontSize: 13 }}>
        Company-wide (shared) expenses of {formatInr(data.shared_expenses.month)} this month and {formatInr(data.shared_expenses.year)} this year are not allocated to Abroad
        Education on this page.
      </p>
      <p>
        <Link className="kpi-link" href={abroadLedgerHref(data.month)}>Open {formatMonth(data.month)}&apos;s Abroad lines in the ledger</Link>
      </p>
    </>
  );
}
