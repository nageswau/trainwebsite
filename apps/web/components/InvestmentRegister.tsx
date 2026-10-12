import Link from "next/link";

import { formatCalendarDate } from "@/lib/formatDate";
import {
  INVESTMENT_STATUS_LABEL,
  INVESTMENT_VERTICAL_LABEL,
  investmentsHref,
  MANAGEMENT_INVESTMENTS,
  roiText,
  rupees,
  type Investment,
  type InvestmentFilters,
  type InvestmentPage,
} from "@/lib/investments";

// mgmt-014 (EVID-017 §23, MI8/MI9): the investment register -- totals over every match (cancelled left out), a GET filter form (refresh,
// back and shared links keep it, as on Management activity), the table and paging. `data` is null when the read failed or the API refused
// the filters; the form stays so they can be fixed.
export const investorText = (i: Pick<Investment, "investor_kind" | "investor">) => (i.investor_kind === "company" ? "Company" : (i.investor?.full_name ?? "—"));

export default function InvestmentRegister({ data, error, filters }: { data: InvestmentPage | null; error: string; filters: InvestmentFilters }) {
  const select = (name: "vertical" | "status", label: string, all: string, labels: Record<string, string>) => (
    <div className="field" style={{ margin: 0 }}>
      <label htmlFor={`investments-${name}`}>{label}</label>
      <select id={`investments-${name}`} name={name} defaultValue={filters[name]}>
        <option value="">{all}</option>
        {Object.entries(labels).map(([value, text]) => <option key={value} value={value}>{text}</option>)}
      </select>
    </div>
  );

  return (
    <div className="action-card" style={{ display: "grid", gap: 12 }}>
      {data && (
        <ul className="metric-grid snapshot-tiles" aria-label="Investment totals">
          <li className="metric"><span>Investments</span><strong>{data.totals.count.toLocaleString("en-IN")}</strong></li>
          <li className="metric"><span>Total invested</span><strong>{rupees(data.totals.invested)}</strong></li>
          <li className="metric"><span>Actual return</span><strong>{rupees(data.totals.actual_return)}</strong></li>
          <li className="metric"><span>Overall ROI</span><strong>{roiText(data.totals.roi)}</strong></li>
        </ul>
      )}
      {data && <p className="muted" style={{ margin: 0, fontSize: 13 }}>Totals cover every investment matching the filters except cancelled ones. ROI counts only investments whose actual return is known.</p>}
      {error && <p className="form-error" role="alert">{error}</p>}
      <form method="get" action={MANAGEMENT_INVESTMENTS} aria-label="Investment filters" className="analytics-form">
        {(["date_from", "date_to"] as const).map((name) => (
          <div className="field" style={{ margin: 0 }} key={name}>
            <label htmlFor={`investments-${name}`}>{name === "date_from" ? "From" : "To"}</label>
            <input id={`investments-${name}`} className="input" type="date" name={name} defaultValue={filters[name]} />
          </div>
        ))}
        {select("vertical", "Vertical", "All verticals", INVESTMENT_VERTICAL_LABEL)}
        {select("status", "Status", "All statuses", INVESTMENT_STATUS_LABEL)}
        <button className="btn" type="submit">Apply</button>
        <Link className="btn secondary" href={MANAGEMENT_INVESTMENTS}>Clear filters</Link>
      </form>
      {data && data.items.length === 0 && <p className="empty" role="status">No investments match these filters.</p>}
      {data && data.items.length > 0 && (
        <>
          <div className="table-scroll" role="region" aria-label="Investments, scrollable" tabIndex={0}>
            <table className="table">
              <caption className="visually-hidden">Investments</caption>
              <thead>
                <tr>
                  <th scope="col">Investment ID</th><th scope="col">Date</th><th scope="col">Purpose</th><th scope="col">Vertical</th><th scope="col">Investor</th>
                  <th scope="col">Amount</th><th scope="col">Expected return</th><th scope="col">Actual return</th><th scope="col">ROI</th><th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((i) => (
                  <tr key={i.id}>
                    <th scope="row"><Link href={`${MANAGEMENT_INVESTMENTS}/${i.id}`}>{i.code}</Link></th>
                    <td>{formatCalendarDate(i.invested_on)}</td>
                    <td style={{ overflowWrap: "anywhere" }}>{i.purpose}</td>
                    <td>{INVESTMENT_VERTICAL_LABEL[i.vertical] ?? i.vertical}</td>
                    <td>{investorText(i)}</td>
                    <td>{rupees(i.amount)}</td>
                    <td>{rupees(i.expected_return)}</td>
                    <td>{rupees(i.actual_return)}</td>
                    <td>{roiText(i.roi)}</td>
                    <td><span className="badge">{INVESTMENT_STATUS_LABEL[i.status] ?? i.status}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.total > data.limit && (
            <nav aria-label="Investment pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
              <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
              {data.offset > 0 && <Link className="btn secondary small" aria-label="Previous page" href={investmentsHref({ ...filters, offset: Math.max(0, data.offset - data.limit) })}>Previous</Link>}
              {data.offset + data.limit < data.total && <Link className="btn secondary small" aria-label="Next page" href={investmentsHref({ ...filters, offset: data.offset + data.limit })}>Next</Link>}
            </nav>
          )}
        </>
      )}
    </div>
  );
}
