import Link from "next/link";

import ReportDownloadButton from "@/components/ReportDownloadButton";
import {
  ACCOUNTS_COLUMNS, ACCOUNTS_TABS, GROUP_LABEL, KIND_LABEL, MODE_LABEL, STATE_LABEL, accountsHref, accountsTotals, exportUrl, inr, takes,
  type AccountsPage, type AccountsParams, type AccountsReport, type AccountsRow,
} from "@/lib/itAccounts";

const EMPTY = "Nothing matches these filters.";
const options = (labels: Record<string, string>) => Object.entries(labels).map(([value, label]) => ({ value, label }));

// itc-017 (DEC-SCOPE-367): the IT accounts workspace -- a strip of report links (each report is its own address), a GET filter form (no
// client JS), the totals of the whole filtered list, the page of rows and its CSV. `page` null + `error` = the read failed or the API
// refused the filters (422 text shown above the form, which keeps the inputs). `studentLinks` (the IT Admin) links a row to the student
// record; the accountant has no such page. On a phone the table stacks into labelled blocks (`.table.stack`).
export default function ItAccountsWorkspace({ report, page, error, params, basePath, studentLinks = false }: {
  report: AccountsReport; page: AccountsPage | null; error: string; params: AccountsParams; basePath: string; studentLinks?: boolean;
}) {
  const tab = ACCOUNTS_TABS.find((t) => t.key === report)!;
  const field = (name: keyof AccountsParams, label: string, all: string | null, choices: { value: string; label: string }[]) => (
    <div className="field" style={{ margin: 0 }}>
      <label htmlFor={`accounts-${name}`}>{label}</label>
      <select id={`accounts-${name}`} name={name} defaultValue={String(params[name] ?? "")}>
        {all !== null && <option value="">{all}</option>}
        {/* A value from the address that is not offered (refused with a 422) stays visible beside the message. */}
        {params[name] && !choices.some((c) => c.value === params[name]) && <option value={String(params[name])}>{String(params[name])}</option>}
        {choices.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
      </select>
    </div>
  );
  const courses = (page?.courses ?? []).map((c) => ({ value: c.id, label: c.title }));
  // Without client JS the batch list cannot follow the course box live: once a course is applied, only its batches are offered.
  const batches = (page?.batches ?? []).filter((b) => !params.program_id || b.program_id === params.program_id).map((b) => ({ value: b.id, label: b.name }));
  const dates = { date_from: params.date_from ?? page?.filters.date_from ?? "", date_to: params.date_to ?? page?.filters.date_to ?? "" };
  const columns = ACCOUNTS_COLUMNS[report];
  const student = (row: AccountsRow) =>
    studentLinks && row.student_id ? <Link href={`/it/admin/students/${row.student_id}/profile`}>{columns[0].show(row[columns[0].key])}</Link> : columns[0].show(row[columns[0].key]);

  return (
    <div className="action-card agent-reports">
      <nav aria-label="Accounts reports" className="report-tablist wrap">
        {ACCOUNTS_TABS.map((t) => (
          <Link key={t.key} className="s360-tab" href={accountsHref(basePath, t.key, params)} aria-current={t.key === report ? "page" : undefined}>{t.label}</Link>
        ))}
      </nav>
      <h3>{tab.label}</h3>
      <p className="muted">{tab.about}</p>
      {error && <p className="form-error" role="alert">{error}</p>}
      <form method="get" action={basePath} aria-label="Report filters" className="analytics-form">
        <input type="hidden" name="report" value={report} />
        {field("program_id", "Course", "All courses", courses)}
        {field("batch_id", "Batch", "All batches", batches)}
        {takes(report, "date_from") && (["date_from", "date_to"] as const).map((name) => (
          <div className="field" style={{ margin: 0 }} key={name}>
            <label htmlFor={`accounts-${name}`}>{name === "date_from" ? "From" : "To"}</label>
            <input id={`accounts-${name}`} className="input" type="date" name={name} defaultValue={dates[name] ?? ""} />
          </div>
        ))}
        {takes(report, "group") && field("group", "Group by", null, options(GROUP_LABEL))}
        {takes(report, "mode") && field("mode", "Payment mode", "All modes", options(MODE_LABEL))}
        {takes(report, "kind") && field("kind", "Kind", "All kinds", options(KIND_LABEL))}
        {takes(report, "state") && field("state", "Status", "All owing", options(STATE_LABEL))}
        <button className="btn" type="submit">Apply</button>
        <Link className="btn secondary" href={`${basePath}?report=${report}`}>Clear filters</Link>
      </form>
      {page && (
        <dl className="kpi-grid dashboard-tiles" aria-label={`${tab.label} totals`}>
          {accountsTotals(report, page.totals).map((t) => (
            <div className="kpi-tile" key={t.label}><dt>{t.label}</dt><dd className="kpi-value">{t.value}</dd></div>
          ))}
        </dl>
      )}
      {page && report === "outstanding" && (page.by_course?.length ?? 0) > 0 && (
        <div className="table-scroll" tabIndex={0} role="region" aria-label="Outstanding by course">
          <table className="table compact stack">
            <caption>Outstanding by course</caption>
            <thead><tr><th scope="col">Course</th><th scope="col" className="num">Enrolments owing</th><th scope="col" className="num">Outstanding</th></tr></thead>
            <tbody>
              {page.by_course!.map((c) => (
                <tr key={c.program_id}><th scope="row">{c.title}</th><td data-label="Enrolments owing" className="num">{c.enrolments}</td><td data-label="Outstanding" className="num">{inr(c.balance)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {page && page.items.length === 0 && <p className="empty" role="status">{EMPTY}</p>}
      {page && page.items.length > 0 && (
        <>
          <div className="table-scroll" tabIndex={0} role="region" aria-label={tab.label}>
            <table className="table compact stack">
              <caption className="visually-hidden">{tab.label}</caption>
              <thead><tr>{columns.map((c) => <th key={c.key} scope="col" className={c.num ? "num" : undefined}>{c.label}</th>)}</tr></thead>
              <tbody>
                {page.items.map((row, i) => (
                  <tr key={i}>
                    <th scope="row">{student(row)}</th>
                    {columns.slice(1).map((c) => <td key={c.key} data-label={c.label} className={c.num ? "num" : undefined}>{c.show(row[c.key])}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {page.total > page.limit && (
            <nav aria-label={`${tab.label} pages`} style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
              <span className="muted" style={{ fontSize: 13 }}>Showing {page.offset + 1}–{page.offset + page.items.length} of {page.total}</span>
              {page.offset > 0 && <Link className="btn secondary small" href={accountsHref(basePath, report, params, Math.max(0, page.offset - page.limit))}>Previous</Link>}
              {page.offset + page.limit < page.total && <Link className="btn secondary small" href={accountsHref(basePath, report, params, page.offset + page.limit)}>Next</Link>}
            </nav>
          )}
          <ReportDownloadButton url={exportUrl(report, params)} label="Download CSV" filename={`it-${report}.csv`} contentType="text/csv" busyLabel="Preparing CSV…"
            hint="The CSV holds every row that matches these filters, not just this page." />
        </>
      )}
    </div>
  );
}
