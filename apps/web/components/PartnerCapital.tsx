import Link from "next/link";

import { formatCalendarDate } from "@/lib/formatDate";
import { formatMonth } from "@/lib/managementExpenses";
import { formatInr } from "@/lib/managementLedger";
import {
  CAPITAL_FIGURES,
  CAPITAL_HOME,
  CAPITAL_KIND_LABEL,
  capitalHref,
  isNegative,
  pctText,
  shareTotalWarning,
  type Capital,
  type CapitalFigures,
  type CapitalQuery,
} from "@/lib/partnerCapital";

const money = (amount: string | null) => (amount === null ? "—" : formatInr(amount));

/** One figure in one column: share % as a percentage, money in rupees; a negative balance or profit share in red, the minus sign kept. */
function Figure({ figures, figure }: { figures: CapitalFigures; figure: keyof CapitalFigures }) {
  const value = figures[figure];
  if (figure === "share_pct") return <>{pctText(value)}</>;
  if (!isNegative(value)) return <>{money(value)}</>;
  return (
    <>
      <span className="pnl-loss">{money(value)}</span>
      {figure === "balance" && <><br /><small className="muted">Withdrawals exceed the capital put in</small></>}
    </>
  );
}

// mgmt-015 (EVID-017 §24, spec CP1-CP15): each partner's capital account side by side with the total, the share-total warning, the
// entries (newest first, paged) and the share % history. Server-rendered; the period is a GET form, so refresh, back and shared links
// keep it. `data` is null when the read failed; the form stays so another period can be chosen.
export default function PartnerCapital({ data, error, query }: { data: Capital | null; error: string; query: CapitalQuery }) {
  const range = { month: data?.month ?? query.month, period: data?.period ?? query.period };
  const warning = data ? shareTotalWarning(data.totals.share_pct ?? "0.00") : null;
  return (
    <div className="action-card" style={{ display: "grid", gap: 12 }}>
      {error && <p className="form-error" role="alert">{error}</p>}
      <form key={`${range.month}-${range.period}`} method="get" action={CAPITAL_HOME} aria-label="Choose a period" className="analytics-form" autoComplete="off">
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="capital-month">Profit share up to</label>
          <input id="capital-month" className="input" type="month" name="month" defaultValue={range.month} max={data?.as_of.slice(0, 7)} min="2000-01" />
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="capital-period">Over</label>
          <select id="capital-period" className="input" name="period" defaultValue={range.period}>
            <option value="month">That month</option>
            <option value="quarter">Quarter to date</option>
            <option value="year">Financial year to date</option>
          </select>
        </div>
        <button className="btn" type="submit">Show</button>
      </form>
      {data && (
        <>
          <p className="muted" style={{ margin: 0 }}>
            Capital figures as of {formatCalendarDate(data.as_of)}. Profit share is indicative only, nothing is paid out: {data.label} net profit{" "}
            <span className={isNegative(data.net_profit) ? "pnl-loss" : undefined}>{formatInr(data.net_profit)}</span> × each partner&apos;s share % in force
            that month (from Profit &amp; loss).
          </p>
          {warning && <p className="status pending" role="status" style={{ display: "block", margin: 0, fontSize: 14, borderRadius: 10, padding: "10px 14px" }}>{warning}</p>}
          {data.accounts.length === 0 ? (
            <p className="empty">No partners yet.</p>
          ) : (
            <div className="table-scroll" role="region" aria-label="Capital accounts, scrollable" tabIndex={0}>
              <table className="table">
                <caption className="visually-hidden">Capital accounts</caption>
                <thead>
                  <tr>
                    <th scope="col">Figure</th>
                    {data.accounts.map((a) => (
                      <th scope="col" key={a.partner.id}>
                        {a.partner.full_name}
                        {!a.partner.active && <small className="muted"> (former partner)</small>}
                      </th>
                    ))}
                    <th scope="col">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {CAPITAL_FIGURES.map(({ key, label }) => (
                    <tr key={key}>
                      <th scope="row">{label}</th>
                      {data.accounts.map((a) => <td key={a.partner.id}><Figure figures={a} figure={key} /></td>)}
                      <td><strong><Figure figures={data.totals} figure={key} /></strong></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>
            Capital balance = capital invested + additional investment − withdrawals. Profit distributions are returns and do not change it. Outstanding
            contribution = committed capital − capital put in.
          </p>

          <h3 style={{ margin: "12px 0 0" }}>Capital entries</h3>
          {data.entries.items.length === 0 ? (
            <p className="empty">No capital entries yet.</p>
          ) : (
            <>
              <div className="table-scroll" role="region" aria-label="Capital entries, scrollable" tabIndex={0}>
                <table className="table" style={{ minWidth: 760 }}>
                  <caption className="visually-hidden">Capital entries</caption>
                  <thead>
                    <tr><th scope="col">Date</th><th scope="col">Partner</th><th scope="col">Kind</th><th scope="col">Amount</th><th scope="col">Note</th><th scope="col">Recorded by</th></tr>
                  </thead>
                  <tbody>
                    {data.entries.items.map((e) => (
                      <tr key={e.id}>
                        <td>{formatCalendarDate(e.entry_date)}</td>
                        <td>{e.partner.full_name}</td>
                        <td>{CAPITAL_KIND_LABEL[e.kind] ?? e.kind}</td>
                        <td>{formatInr(e.amount)}</td>
                        <td style={{ overflowWrap: "anywhere" }}>{e.note ?? "—"}</td>
                        <td>{e.created_by.full_name}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {data.entries.total > data.entries.limit && (
                <nav aria-label="Capital entry pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
                  <span className="muted" style={{ fontSize: 13 }}>
                    Showing {data.entries.offset + 1}–{data.entries.offset + data.entries.items.length} of {data.entries.total}
                  </span>
                  {data.entries.offset > 0 && (
                    <Link className="btn secondary small" aria-label="Previous page" href={capitalHref({ ...query, offset: Math.max(0, data.entries.offset - data.entries.limit) })}>Previous</Link>
                  )}
                  {data.entries.offset + data.entries.limit < data.entries.total && (
                    <Link className="btn secondary small" aria-label="Next page" href={capitalHref({ ...query, offset: data.entries.offset + data.entries.limit })}>Next</Link>
                  )}
                </nav>
              )}
            </>
          )}

          <h3 style={{ margin: "12px 0 0" }}>Share % history</h3>
          {data.shares.length === 0 ? (
            <p className="empty">No share % set yet.</p>
          ) : (
            <div className="table-scroll" role="region" aria-label="Share % history, scrollable" tabIndex={0}>
              <table className="table" style={{ minWidth: 640 }}>
                <caption className="visually-hidden">Share % history</caption>
                <thead>
                  <tr><th scope="col">From</th><th scope="col">Partner</th><th scope="col">Share %</th><th scope="col">Committed capital</th><th scope="col">Status</th><th scope="col">Set by</th></tr>
                </thead>
                <tbody>
                  {data.shares.map((s) => (
                    <tr key={s.id}>
                      <td>{formatMonth(s.effective_from.slice(0, 7))}</td>
                      <td>{s.partner.full_name}</td>
                      <td>{pctText(s.share_pct)}</td>
                      <td>{money(s.commitment)}</td>
                      <td>{s.in_force ? <span className="badge">In force</span> : s.effective_from > data.as_of ? "Planned" : "Earlier"}</td>
                      <td>{s.updated_by.full_name}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
