import Link from "next/link";

import {
  formatInr, KIND_LABEL, LEDGER_HOME, ledgerHref, STATUS_LABEL, statusClass, VERTICAL_LABEL, type LedgerCategory, type LedgerFilters, type LedgerPage,
} from "@/lib/managementLedger";

// mgmt-004 (ML10, ML15): the ledger list. A GET form keyed on its own link (a chip or pager link back to this page must not keep the old
// values) with autoComplete off (no browser-restored selects), so refresh, back and shared links keep the filters. `data` is null when
// the read failed; the form stays usable. Totals are the approved entries matching every filter but status.
export default function ManagementLedger({ data, error, filters, categories }: { data: LedgerPage | null; error: string; filters: LedgerFilters; categories: LedgerCategory[] }) {
  const select = (name: "kind" | "category" | "vertical" | "status", label: string, all: string, choices: { value: string; label: string }[]) => (
    <div className="field" style={{ margin: 0 }}>
      <label htmlFor={`ledger-${name}`}>{label}</label>
      <select id={`ledger-${name}`} name={name} defaultValue={filters[name]}>
        <option value="">{all}</option>
        {choices.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
      </select>
    </div>
  );
  const entries = (labels: Record<string, string>) => Object.entries(labels).map(([value, label]) => ({ value, label }));
  const categoryChoices = categories.map((c) => ({ value: c.id, label: c.active ? c.name : `${c.name} (inactive)` }));

  return (
    <div className="action-card">
      {error && <p className="form-error" role="alert">{error}</p>}
      <form key={ledgerHref(filters)} method="get" action={LEDGER_HOME} aria-label="Ledger filters" className="analytics-form" autoComplete="off">
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="ledger-month">Month</label>
          <input id="ledger-month" className="input" type="month" name="month" defaultValue={filters.month} />
        </div>
        {select("kind", "Kind", "Income and expenses", entries(KIND_LABEL))}
        {select("category", "Category", "All categories", categoryChoices)}
        {select("vertical", "Vertical", "All verticals", entries(VERTICAL_LABEL))}
        {select("status", "Status", "Any status", entries(STATUS_LABEL))}
        <button className="btn" type="submit">Apply</button>
        <Link className="btn secondary" href={LEDGER_HOME}>Clear filters</Link>
      </form>
      {data && (
        <>
          <ul aria-label="Approved totals" className="kpi-grid" style={{ listStyle: "none", padding: 0 }}>
            {([["income", "Approved income"], ["expense", "Approved expenses"], ["net", "Net (income − expenses)"]] as const).map(([key, label]) => (
              <li key={key} className="kpi-tile">
                <dl style={{ margin: 0 }}>
                  <dt>{label}</dt>
                  <dd className="kpi-value">{formatInr(data.totals[key])}</dd>
                </dl>
              </li>
            ))}
          </ul>
          <p className="muted" style={{ fontSize: 13 }}>Only approved entries count in the totals; drafts, entries awaiting approval and rejected entries are listed but not counted.</p>
          {data.items.length === 0 ? (
            <p className="empty" role="status">No ledger entries match these filters.</p>
          ) : (
            // QA-03: on a phone the table scrolls sideways in its own focusable region instead of squeezing the entry to a word per line.
            <div className="table-wrap" role="region" aria-label="Ledger entries" tabIndex={0} style={{ overflowX: "auto" }}>
              <table className="table" style={{ minWidth: 720 }}>
                <caption className="visually-hidden">Ledger entries, newest first</caption>
                <thead>
                  <tr><th scope="col">Date</th><th scope="col">Entry</th><th scope="col">Category</th><th scope="col">Vertical</th><th scope="col">Status</th><th scope="col" style={{ textAlign: "right" }}>Amount</th></tr>
                </thead>
                <tbody>
                  {data.items.map((item) => (
                    <tr key={item.id}>
                      <td style={{ whiteSpace: "nowrap" }}>{item.entry_date}</td>
                      <td style={{ overflowWrap: "anywhere" }}>
                        <Link className="kpi-link" href={`${LEDGER_HOME}/${item.id}`}>{item.description}</Link>
                        <div className="muted" style={{ fontSize: 13 }}>{KIND_LABEL[item.kind]}{item.reversal_of_id ? " · reversal" : ""}</div>
                      </td>
                      <td>{item.category.name}</td>
                      <td>{VERTICAL_LABEL[item.vertical] ?? item.vertical}</td>
                      <td><span className={statusClass(item.status)}>{STATUS_LABEL[item.status]}</span></td>
                      <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>{item.reversal_of_id ? "−" : ""}{formatInr(item.amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {data.total > data.limit && (
            <nav aria-label="Ledger pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
              <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
              {data.offset > 0 && <Link className="btn secondary small" aria-label="Previous page" href={ledgerHref({ ...filters, offset: Math.max(0, data.offset - data.limit) })}>Previous</Link>}
              {data.offset + data.limit < data.total && <Link className="btn secondary small" aria-label="Next page" href={ledgerHref({ ...filters, offset: data.offset + data.limit })}>Next</Link>}
            </nav>
          )}
        </>
      )}
    </div>
  );
}
