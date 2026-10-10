import Link from "next/link";

import ReportDownloadButton from "@/components/ReportDownloadButton";
import {
  type PartnershipReport, type PartnershipReportKind, type PartnershipReportParams, type PartnershipReportRow, REPORT_FILTERS, REPORT_TABS,
  REPORTS_PATH, WINDOW_OPTIONS, csvUrl, reportQuery, tabHref,
} from "@/lib/partnershipReports";

const EMPTY: Record<PartnershipReportKind, string> = {
  pipeline: "No universities in your scope yet.",
  expected: "No universities match this expected date window.",
  performance: "No university had any student activity in this period, and none in your scope is a partner yet.",
  agreements: "No agreements expire in the next 90 days.",
  targets: "No partnership managers in your scope for this month.",
};

const show = (value: string | number | null | undefined) => (value === null || value === undefined || value === "" ? "—" : String(value));

// upc-031 (DEC-SCOPE-173, spec §5): one partnership report -- the tel-024 layout. A strip of report links (each report is its own
// address, so a view can be shared and Back works), a plain GET filter form for the reports that have filters (no client JS), the
// table and its CSV. Columns, labels and the Total row are the server's. On a phone the table stacks into labelled blocks
// (`.table.stack`). `report` null + `error` = the read failed or the API refused the inputs; the form stays so they can be corrected.
export default function PartnershipReportView({ kind, report, error, params }: {
  kind: PartnershipReportKind; report: PartnershipReport | null; error: string; params: PartnershipReportParams;
}) {
  const filters = REPORT_FILTERS[kind];
  // The address's value first (kept after a refusal), else the value the report used (its default).
  const value = (name: keyof PartnershipReportParams) => params[name] ?? report?.filters[name] ?? "";
  const input = (name: "from" | "to" | "month", label: string, type: string) => (
    <div className="field" style={{ margin: 0 }} key={name}>
      <label htmlFor={`report-${name}`}>{label}</label>
      <input id={`report-${name}`} className="input" type={type} name={name} defaultValue={value(name)} />
    </div>
  );
  const [first, ...rest] = report?.columns ?? [];
  const cells = (row: PartnershipReportRow) => (
    <>
      <th scope="row">{show(row[first.key])}</th>
      {rest.map((c) => <td key={c.key} data-label={c.label} className={c.numeric ? "num" : undefined}>{show(row[c.key])}</td>)}
    </>
  );

  return (
    <div className="action-card agent-reports">
      <nav aria-label="Reports" className="report-tablist">
        {REPORT_TABS.map((t) => (
          <Link key={t.key} className="s360-tab" href={tabHref(t.key)} aria-current={t.key === kind ? "page" : undefined}>{t.label}</Link>
        ))}
      </nav>
      <h3>{report?.title ?? `${REPORT_TABS.find((t) => t.key === kind)?.label} Report`}</h3>
      {error && <p className="form-error" role="alert">{error}</p>}
      {filters.length > 0 && (
        // Keyed on the address: an uncontrolled form would keep its old values after a client navigation to the same page; and
        // autoComplete off stops the browser restoring a remembered value over the address's on Back (QA31-01).
        <form key={`${kind}${reportQuery(kind, params)}`} method="get" action={REPORTS_PATH} aria-label="Report filters" className="analytics-form" autoComplete="off">
          <input type="hidden" name="report" value={kind} />
          {filters.includes("window") && (
            <div className="field" style={{ margin: 0 }}>
              <label htmlFor="report-window">Expected date window</label>
              <select id="report-window" name="window" defaultValue={value("window") || "all"}>
                {WINDOW_OPTIONS.map((w) => <option key={w.value} value={w.value}>{w.label}</option>)}
              </select>
            </div>
          )}
          {filters.includes("from") && input("from", "From", "date")}
          {filters.includes("to") && input("to", "To", "date")}
          {filters.includes("month") && input("month", "Month", "month")}
          <button className="btn" type="submit">Apply</button>
          <Link className="btn secondary" href={tabHref(kind)}>Clear filters</Link>
        </form>
      )}
      {report?.notes.map((note) => <p key={note} className="muted">{note}</p>)}
      {report && report.items.length === 0 && <p className="empty" role="status">{EMPTY[kind]}</p>}
      {report && report.items.length > 0 && (
        <>
          {report.truncated && (
            <p className="muted">{`Showing the first ${report.items.length} of ${report.total} rows. Download the CSV for all of them.`}</p>
          )}
          <div className="table-scroll" tabIndex={0} role="region" aria-label={report.title}>
            <table className="table compact stack">
              <caption className="visually-hidden">{`${report.title}, as of ${report.as_of}`}</caption>
              <thead>
                <tr>{report.columns.map((c) => <th key={c.key} scope="col" className={c.numeric ? "num" : undefined}>{c.label}</th>)}</tr>
              </thead>
              <tbody>{report.items.map((row, i) => <tr key={i}>{cells(row)}</tr>)}</tbody>
              {report.totals && <tfoot><tr>{cells(report.totals)}</tr></tfoot>}
            </table>
          </div>
          <ReportDownloadButton
            url={csvUrl(kind, params)} label="Download CSV" busyLabel="Preparing CSV…" contentType="text/csv"
            filename={`partnership-${kind}-${report.as_of}.csv`}
          />
        </>
      )}
    </div>
  );
}
