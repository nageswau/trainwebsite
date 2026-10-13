import Link from "next/link";

import { formatCalendarDate } from "@/lib/formatDate";
import { formatMonth } from "@/lib/managementExpenses";
import {
  IT_REVENUE_HOME, PAGE_SIZE, itRevenueHref, type ItRevenue, type ItRevenuePaymentPage, type ItRevenueQuery, type Money, type Scope,
} from "@/lib/managementItRevenue"; // prettier-ignore
import { formatInr, formatMoney } from "@/lib/managementLedger";

const UNLINKED = "Not linked to a course";

/** Who the payment list is for, in words (IR11); a course or batch with no figures in the period is named generically. */
function scopeName(data: ItRevenue | null, scope: Scope): string {
  if ("unlinked" in scope) return UNLINKED;
  for (const course of data?.courses ?? []) {
    if ("program" in scope && course.program_id === scope.program) return course.title;
    const batch = "batch" in scope ? course.batches.find((b) => b.batch_id === scope.batch) : undefined;
    if (batch) return `${course.title} · ${batch.name}`;
  }
  return "program" in scope ? "the chosen course" : "the chosen batch";
}

function shown(money: Money): boolean {
  return Number(money.revenue) !== 0 || Number(money.costs) !== 0;
}

// mgmt-007 (EVID-017 §5, spec IR1-IR12): IT Training revenue for the finance tier -- the four figures, revenue per course with its
// batches beneath, the "Not linked to a course" row so the course rows add up to the total, income by kind, costs by kind, and the
// payments of a chosen course / batch. Server-rendered; the period and the payment list live in the address (GET form and links),
// so refresh, back and shared links keep them.
export default function ManagementItRevenue({
  data, error, query, maxMonth, payments, paymentsError,
}: { data: ItRevenue | null; error: string; query: ItRevenueQuery; maxMonth: string; payments: ItRevenuePaymentPage | null; paymentsError: string }) { // prettier-ignore
  const range = { month: data?.month ?? query.month, period: data?.period ?? query.period };
  const payLink = (scope: Scope, label: string) => (
    <Link className="kpi-link" href={itRevenueHref(range, scope)} aria-label={`Payments: ${label}`}>Payments</Link>
  );
  const empty = data && data.courses.length === 0 && !shown(data.unlinked);
  return (
    <div className="action-card">
      {error && <p className="form-error" role="alert">{error}</p>}
      <form key={`${range.month}-${range.period}`} method="get" action={IT_REVENUE_HOME} aria-label="Choose a period" className="analytics-form" autoComplete="off">
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="it-revenue-month">Month</label>
          <input id="it-revenue-month" className="input" type="month" name="month" defaultValue={range.month} max={maxMonth} min="2000-01" />
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="it-revenue-period">Show</label>
          <select id="it-revenue-period" className="input" name="period" defaultValue={range.period}>
            <option value="month">That month</option>
            <option value="year">Financial year to date</option>
          </select>
        </div>
        <button className="btn" type="submit">Show</button>
      </form>
      {data && (
        <>
          <p className="muted">
            {data.label}: {formatCalendarDate(data.start)} to {formatCalendarDate(data.end)}. Paid IT payments and approved IT ledger entries, in rupees. Company-wide
            shared costs (rent, salaries) are not split across courses here.
          </p>
          {data.not_counted.length > 0 && (
            <p className="muted" style={{ fontSize: 13 }}>
              IT payments in another currency are not counted: {data.not_counted.map((n) => `${formatMoney(n.amount, n.currency)} (${n.count} ${n.count === 1 ? "payment" : "payments"})`).join(", ")}.
            </p>
          )}
          <ul className="metric-grid snapshot-tiles money-tiles accounts-tiles" aria-label="IT Training figures">
            <li className="metric"><span>Revenue</span><strong>{formatInr(data.totals.revenue)}</strong></li>
            <li className="metric"><span>Costs</span><strong>{formatInr(data.totals.costs)}</strong></li>
            <li className="metric"><span>Contribution</span><strong>{formatInr(data.totals.contribution)}</strong></li>
            <li className="metric"><span>New enrolments</span><strong>{data.totals.enrolments}</strong></li>
          </ul>
          {empty ? (
            <p className="empty" role="status">No IT Training revenue, costs or enrolments in {data.period === "year" ? `the ${data.label.toLowerCase()}` : formatMonth(data.month)}.</p>
          ) : (
            <>
              <h3 id="it-revenue-courses">Revenue per course</h3>
              <div className="table-wrap" role="region" aria-labelledby="it-revenue-courses" tabIndex={0} style={{ overflowX: "auto" }}>
                <table className="table" style={{ minWidth: 640 }}>
                  <caption className="visually-hidden">Revenue per course</caption>
                  <thead>
                    <tr><th scope="col">Course / batch</th><th scope="col">New enrolments</th><th scope="col">Revenue</th><th scope="col">Costs</th><th scope="col">Contribution</th><th scope="col"><span className="visually-hidden">Payments</span></th></tr>
                  </thead>
                  {data.courses.map((course) => (
                    <tbody key={course.program_id}>
                      <tr>
                        <th scope="row">{course.title}</th>
                        <td>{course.enrolments}</td>
                        <td><strong>{formatInr(course.revenue)}</strong></td>
                        <td>{formatInr(course.costs)}</td>
                        <td>{formatInr(course.contribution)}</td>
                        <td>{payLink({ program: course.program_id }, course.title)}</td>
                      </tr>
                      {course.batches.map((batch) => (
                        <tr key={batch.batch_id}>
                          <th scope="row" className="it-revenue-batch">{batch.name}</th>
                          <td>{batch.enrolments}</td>
                          <td>{formatInr(batch.revenue)}</td>
                          <td>{formatInr(batch.costs)}</td>
                          <td />
                          <td>{payLink({ batch: batch.batch_id }, `${course.title} · ${batch.name}`)}</td>
                        </tr>
                      ))}
                      {shown(course.unbatched) && (
                        <tr>
                          <th scope="row" className="it-revenue-batch">Course-wide entries</th>
                          <td />
                          <td>{formatInr(course.unbatched.revenue)}</td>
                          <td>{formatInr(course.unbatched.costs)}</td>
                          <td />
                          <td />
                        </tr>
                      )}
                    </tbody>
                  ))}
                  <tfoot>
                    {shown(data.unlinked) && (
                      <tr>
                        <th scope="row">{UNLINKED}</th>
                        <td />
                        <td>{formatInr(data.unlinked.revenue)}</td>
                        <td>{formatInr(data.unlinked.costs)}</td>
                        <td />
                        <td>{payLink({ unlinked: true }, UNLINKED)}</td>
                      </tr>
                    )}
                    <tr>
                      <th scope="row">Total</th>
                      <td><strong>{data.totals.enrolments}</strong></td>
                      <td><strong>{formatInr(data.totals.revenue)}</strong></td>
                      <td><strong>{formatInr(data.totals.costs)}</strong></td>
                      <td><strong>{formatInr(data.totals.contribution)}</strong></td>
                      <td />
                    </tr>
                  </tfoot>
                </table>
              </div>
            </>
          )}
          <div className="it-revenue-split">
            {([["it-revenue-income", "Income by kind", data.income, data.totals.revenue], ["it-revenue-costs", "Costs by kind", data.costs, data.totals.costs]] as const).map(([id, title, lines, total]) => (
              <section key={id} aria-labelledby={id}>
                <h3 id={id}>{title}</h3>
                <table className="table" style={{ minWidth: 0 }}>
                  <caption className="visually-hidden">{title}</caption>
                  <tbody>
                    {lines.map((line) => (
                      <tr key={line.key}><th scope="row">{line.label}</th><td>{formatInr(line.amount)}</td></tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr><th scope="row">Total</th><td><strong>{formatInr(total)}</strong></td></tr>
                  </tfoot>
                </table>
              </section>
            ))}
          </div>
          <p className="muted">
            <strong>Placement revenue:</strong> not tracked. Recruitment invoices are raised per job, not per student, so they cannot be traced to IT
            students. Recruitment revenue has its own dashboard.
          </p>
        </>
      )}
      {query.scope && (
        <section id="payments" aria-labelledby="it-revenue-payments">
          <h3 id="it-revenue-payments">Payments: {scopeName(data, query.scope)}</h3>
          {paymentsError && <p className="form-error" role="alert">{paymentsError}</p>}
          {payments && payments.items.length === 0 && <p className="empty" role="status">No counted payments in this period.</p>}
          {payments && payments.items.length > 0 && (
            <>
              <div className="table-wrap" role="region" aria-label="Payment list" tabIndex={0} style={{ overflowX: "auto" }}>
                <table className="table" style={{ minWidth: 720 }}>
                  <caption className="visually-hidden">Payments</caption>
                  <thead>
                    <tr><th scope="col">Date</th><th scope="col">Enrolment</th><th scope="col">Course</th><th scope="col">Batch</th><th scope="col">Kind</th><th scope="col">Receipt</th><th scope="col">Amount</th></tr>
                  </thead>
                  <tbody>
                    {payments.items.map((p) => (
                      <tr key={p.id}>
                        <td>{formatCalendarDate(p.entry_date)}</td>
                        <td>{p.enrollment_code ?? "—"}</td>
                        <td>{p.course ?? "—"}</td>
                        <td>{p.batch ?? "—"}</td>
                        <td>{p.kind}{p.installment_no ? ` · instalment ${p.installment_no}` : ""}</td>
                        <td>{p.receipt_no ?? "—"}</td>
                        <td>{formatMoney(p.amount, p.currency)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="muted" role="status">
                Showing {payments.offset + 1}–{payments.offset + payments.items.length} of {payments.total}. Student names are not shown.
              </p>
              {payments.total > PAGE_SIZE && (
                <nav aria-label="Payment pages" style={{ display: "flex", gap: 12 }}>
                  {query.page > 1 && <Link className="btn secondary" href={itRevenueHref(range, query.scope, query.page - 1)}>Previous</Link>}
                  {payments.offset + payments.items.length < payments.total && <Link className="btn secondary" href={itRevenueHref(range, query.scope, query.page + 1)}>Next</Link>}
                </nav>
              )}
            </>
          )}
        </section>
      )}
    </div>
  );
}
