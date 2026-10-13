import Link from "next/link";

import { formatCalendarDate } from "@/lib/formatDate";
import { formatMonth } from "@/lib/managementExpenses";
import { formatInr } from "@/lib/managementLedger";
import { RECRUITMENT_REVENUE_HOME, type RecruitmentKpis, type RecruitmentRevenue, type RecruitmentRevenueQuery } from "@/lib/managementRecruitmentRevenue";

// EVID-017 §6's KPIs, in source order. "—" when there is nothing to divide by (RR7, RR8).
const KPIS: [keyof RecruitmentKpis, string][] = [
  ["recruiters", "Recruiters"], ["partner_companies", "Partner companies"], ["open_positions", "Open positions"], ["candidates", "Candidates"],
  ["interviews", "Interviews"], ["selections", "Selections"], ["joining", "Joining"], ["placement_pct", "Placement percentage"],
  ["revenue_per_placement", "Revenue per placement"],
]; // prettier-ignore

function shown(key: keyof RecruitmentKpis, value: number | string | null): string {
  if (value === null) return "—";
  if (key === "placement_pct") return `${Number(value).toFixed(1)}%`;
  return key === "revenue_per_placement" ? formatInr(String(value)) : String(value);
}

// mgmt-008 (EVID-017 §6, spec RR1-RR12): the nine KPIs for every management role and, for the finance tier only, Recruitment revenue by
// kind. Server-rendered; the period lives in the address (GET form), so refresh, back and shared links keep it.
export default function ManagementRecruitmentRevenue({
  data, error, query, maxMonth,
}: { data: RecruitmentRevenue | null; error: string; query: RecruitmentRevenueQuery; maxMonth: string }) { // prettier-ignore
  const range = { month: data?.month ?? query.month, period: data?.period ?? query.period };
  const kpis = KPIS.filter(([key]) => data?.revenue_visible || key !== "revenue_per_placement");
  const revenue = data?.revenue;
  const empty = revenue && revenue.kinds.every((kind) => Number(kind.amount) === 0);
  return (
    <div className="action-card">
      {error && <p className="form-error" role="alert">{error}</p>}
      <form key={`${range.month}-${range.period}`} method="get" action={RECRUITMENT_REVENUE_HOME} aria-label="Choose a period" className="analytics-form" autoComplete="off">
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="recruitment-revenue-month">Month</label>
          <input id="recruitment-revenue-month" className="input" type="month" name="month" defaultValue={range.month} max={maxMonth} min="2000-01" />
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="recruitment-revenue-period">Show</label>
          <select id="recruitment-revenue-period" className="input" name="period" defaultValue={range.period}>
            <option value="month">That month</option>
            <option value="year">Financial year to date</option>
          </select>
        </div>
        <button className="btn" type="submit">Show</button>
      </form>
      {data && (
        <>
          <p className="muted">
            {data.label}: {formatCalendarDate(data.start)} to {formatCalendarDate(data.end)}. Candidates, interviews, selections and joining are
            counted to {formatCalendarDate(data.kpi_end)}, as on Recruiter Performance; recruiters, partner companies and open positions are as of today.
          </p>
          <ul className="metric-grid snapshot-tiles" aria-label="Recruitment KPIs">
            {kpis.map(([key, label]) => (
              <li key={key} className="metric"><span>{label}</span><strong>{shown(key, data.kpis[key])}</strong></li>
            ))}
          </ul>
          {revenue && (
            <section>
              <h3 id="recruitment-revenue-kinds">Revenue by kind</h3>
              {empty ? (
                <p className="empty" role="status">No recruitment revenue in {data.period === "year" ? `the ${data.label.toLowerCase()}` : formatMonth(data.month)}.</p>
              ) : (
                <div className="table-wrap" role="region" aria-labelledby="recruitment-revenue-kinds" tabIndex={0} style={{ overflowX: "auto" }}>
                  <table className="table" style={{ minWidth: 0 }}>
                    <caption className="visually-hidden">Revenue by kind</caption>
                    <tbody>
                      {revenue.kinds.map((kind) => (
                        <tr key={kind.key}><th scope="row">{kind.label}</th><td>{formatInr(kind.amount)}</td></tr>
                      ))}
                    </tbody>
                    <tfoot>
                      <tr><th scope="row">Total</th><td><strong>{formatInr(revenue.total)}</strong></td></tr>
                    </tfoot>
                  </table>
                </div>
              )}
              <p className="muted">
                Recruiter invoice payments are the fees received against recruitment invoices. Internship programs, corporate training and other
                employer revenue count once they are approved as Recruitment income in the <Link href="/management/ledger">ledger</Link>, each under its own category.
              </p>
            </section>
          )}
        </>
      )}
    </div>
  );
}
