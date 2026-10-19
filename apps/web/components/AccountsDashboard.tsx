import { amountText, type AccountsMonth, type AccountsSection, type NotCounted } from "@/lib/accounts";
import { rupees } from "@/lib/investments";
import { monthLabel } from "@/lib/salaries";

const notCountedText = (rows: NotCounted[]) =>
  rows.map((r) => `${r.currency} ${r.amount} ${r.kind} (${r.count} ${r.count === 1 ? "line" : "lines"})`).join(" · ");

// mgmt-013 (EVID-017 §22, spec AD2-AD6, AD13): the month's income and expense heads (each with the ledger categories it holds, so the
// mapping is visible), and the financial position. Read-only; the balances form sits beside it.
function HeadTable({ section, title, totalLabel }: { section: AccountsSection; title: string; totalLabel: string }) {
  return (
    <div className="table-wrap">
      <table className="table accounts-heads" aria-label={title}>
        <thead>
          <tr>
            <th scope="col">Head</th>
            <th scope="col">Amount</th>
            <th scope="col">From</th>
          </tr>
        </thead>
        <tbody>
          {section.heads.map((h) => (
            <tr key={h.key}>
              <th scope="row">{h.label}</th>
              <td>{rupees(h.amount)}</td>
              <td className="muted" style={{ fontSize: 13, overflowWrap: "anywhere" }}>
                {h.parts.length ? h.parts.map((p) => `${p.label} ${rupees(p.amount)}`).join(" · ") : "—"}
              </td>
            </tr>
          ))}
          <tr>
            <th scope="row">{totalLabel}</th>
            <td><strong>{rupees(section.total)}</strong></td>
            <td />
          </tr>
        </tbody>
      </table>
    </div>
  );
}

export default function AccountsDashboard({ data }: { data: AccountsMonth }) {
  const label = monthLabel(data.month);
  const r = data.receivables;
  const b = data.balances;
  const asOf = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(`${data.as_of}T00:00:00Z`));
  return (
    <>
      <section className="action-card" aria-labelledby="accounts-position" style={{ display: "grid", gap: 12 }}>
        <h3 id="accounts-position" style={{ margin: 0 }}>Financial position</h3>
        <ul className="metric-grid snapshot-tiles money-tiles accounts-tiles" aria-label="Financial position">
          <li className="metric"><span>Receivables</span><strong>{rupees(r.total)}</strong><small className="muted">{rupees(r.overdue)} overdue</small></li>
          <li className="metric"><span>Payables</span><strong>{amountText(b.payables)}</strong></li>
          <li className="metric"><span>Cash/bank</span><strong>{amountText(b.cash_bank)}</strong></li>
          <li className="metric"><span>Profit</span><strong>{amountText(data.profit)}</strong><small className="muted">{label}</small></li>
          <li className="metric"><span>Tax liabilities</span><strong>{amountText(b.tax_liabilities)}</strong></li>
          <li className="metric">
            <span>Pending invoices</span><strong>{rupees(data.pending_invoices.amount)}</strong>
            <small className="muted">{data.pending_invoices.count} {data.pending_invoices.count === 1 ? "invoice" : "invoices"}</small>
          </li>
        </ul>
        <ul className="muted" aria-label="Receivables by source" style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
          <li>Student fees: {rupees(r.fees)}</li>
          <li>Recruitment invoices: {rupees(r.recruitment)}</li>
          {r.university !== null && <li>University commission: {rupees(r.university)}</li>}
        </ul>
        {!data.commission_visible && <p className="muted" style={{ margin: 0, fontSize: 13 }}>University commission is not included: only partners see it.</p>}
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>
          Receivables and pending invoices are what is owed today ({asOf}):{" "}
          {data.commission_visible
            ? "unpaid student fees, open recruitment invoices and university commission still expected. University commission has no invoices, so it is not in pending invoices."
            : "unpaid student fees and open recruitment invoices."}{" "}
          Payables, cash/bank and tax liabilities are the month-end figures entered below; profit is {label}&apos;s income less expenses.
          {r.not_counted.length > 0 && <> Not added (another currency): {notCountedText(r.not_counted)}.</>}
        </p>
      </section>

      <section className="action-card" aria-labelledby="accounts-income" style={{ display: "grid", gap: 12 }}>
        <h3 id="accounts-income" style={{ margin: 0 }}>Income · {label}</h3>
        <HeadTable section={data.income} title={`Income by head, ${label}`} totalLabel="Total income" />
      </section>

      <section className="action-card" aria-labelledby="accounts-expenses" style={{ display: "grid", gap: 12 }}>
        <h3 id="accounts-expenses" style={{ margin: 0 }}>Expenses · {label}</h3>
        <HeadTable section={data.expenses} title={`Expenses by head, ${label}`} totalLabel="Total expenses" />
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>
          Approved ledger entries and automatic lines in rupees (salaries, agent commissions, trip expenses). Categories not named in a head
          are counted under Operations.
          {data.not_counted.length > 0 && <> Not counted (another currency): {notCountedText(data.not_counted)}.</>}
        </p>
      </section>
    </>
  );
}
