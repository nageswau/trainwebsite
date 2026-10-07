import Link from "next/link";

import ReportDownloadButton from "@/components/ReportDownloadButton";
import {
  REPORT_TABS, TEAM_LABEL, type ReportKind, type ReportParams, type ReportRow, type TelecallerReport, csvUrl, tabHref,
} from "@/lib/telecallerReports";

const EMPTY: Partial<Record<ReportKind, string>> = { telecaller: "No telecallers in your scope.", handover: "No leads with a counselor in this range." };

const show = (value: string | number | undefined) => (value === undefined || value === "" ? "—" : String(value));

// tel-024 (DEC-SCOPE-108, EVID-019 §21): one management report -- a strip of report links (each report is its own address, so a view
// can be shared and Back works), a plain GET filter form (no client JS), the table and its CSV. The columns, labels and options are the
// server's; counts are text nodes only. On a phone the table stacks into labelled blocks (`.table.stack`). `report` null + `error` =
// the read failed or the API refused the inputs; the form stays so the inputs can be corrected.
export default function TelecallerReportView({ kind, report, error, params, basePath }: {
  kind: ReportKind; report: TelecallerReport | null; error: string; params: ReportParams; basePath: string;
}) {
  const options = report?.options;
  const leadReport = kind !== "telecaller";
  const select = (name: keyof ReportParams, label: string, all: string, choices: { value: string; label: string }[]) => (
    <div className="field" style={{ margin: 0 }}>
      <label htmlFor={`report-${name}`}>{label}</label>
      <select id={`report-${name}`} name={name} defaultValue={params[name] ?? ""}>
        <option value="">{all}</option>
        {/* A value from the address that is not offered (refused with a 422) stays visible beside the message. */}
        {params[name] && !choices.some((c) => c.value === params[name]) && <option value={params[name]}>{params[name]}</option>}
        {choices.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
      </select>
    </div>
  );
  const [first, ...rest] = report?.columns ?? [];
  const cells = (row: ReportRow) => (
    <>
      <th scope="row">{show(row[first.key])}</th>
      {rest.map((c) => <td key={c.key} data-label={c.label} className={typeof row[c.key] === "number" ? "num" : undefined}>{show(row[c.key])}</td>)}
    </>
  );

  return (
    <div className="action-card agent-reports">
      <nav aria-label="Reports" className="report-tablist">
        {REPORT_TABS.map((t) => (
          <Link key={t.key} className="s360-tab" href={tabHref(basePath, t.key, params)} aria-current={t.key === kind ? "page" : undefined}>{t.label}</Link>
        ))}
      </nav>
      <h3>{`${REPORT_TABS.find((t) => t.key === kind)?.label} Report`}</h3>
      {error && <p className="form-error" role="alert">{error}</p>}
      <form method="get" action={basePath} aria-label="Report filters" className="analytics-form">
        <input type="hidden" name="report" value={kind} />
        {(["date_from", "date_to"] as const).map((name) => (
          <div className="field" style={{ margin: 0 }} key={name}>
            <label htmlFor={`report-${name}`}>{name === "date_from" ? "From" : "To"}</label>
            <input id={`report-${name}`} className="input" type="date" name={name} defaultValue={params[name] ?? report?.[name] ?? ""} />
          </div>
        ))}
        {/* A team to pick only when there is a choice; without options (a failed read) only a team already chosen is kept. */}
        {(options ? options.teams.length > 1 : Boolean(params.team)) && select("team", "Team", "All teams", (options?.teams ?? []).map((t) => ({ value: t, label: TEAM_LABEL[t] ?? t })))}
        {leadReport && select("product_id", "Course", "All courses", (options?.products ?? []).map((p) => ({ value: p.id, label: p.name })))}
        {leadReport && select("campaign_id", "Campaign", "All campaigns", (options?.campaigns ?? []).map((c) => ({ value: c.id, label: c.name })))}
        {leadReport && select("source", "Source", "All sources", (options?.sources ?? []).map((s) => ({ value: s.key, label: s.label })))}
        <button className="btn" type="submit">Apply</button>
        <Link className="btn secondary" href={`${basePath}?report=${kind}`}>Clear filters</Link>
      </form>
      {report && report.items.length === 0 && <p className="empty" role="status">{EMPTY[kind] ?? "No leads in this range."}</p>}
      {report && report.items.length > 0 && (
        <>
          <div className="table-scroll" tabIndex={0} role="region" aria-label={report.title}>
            <table className="table compact stack">
              <caption className="visually-hidden">{`${report.title}, ${report.date_from} to ${report.date_to}`}</caption>
              <thead>
                <tr>{report.columns.map((c, i) => <th key={c.key} scope="col" className={i > 0 && typeof report.totals[c.key] === "number" ? "num" : undefined}>{c.label}</th>)}</tr>
              </thead>
              <tbody>{report.items.map((row, i) => <tr key={i}>{cells(row)}</tr>)}</tbody>
              <tfoot><tr>{cells(report.totals)}</tr></tfoot>
            </table>
          </div>
          <ReportDownloadButton
            url={csvUrl(kind, params)} label="Download CSV" busyLabel="Preparing CSV…" contentType="text/csv"
            filename={`telecaller-${kind}-${report.date_from}-to-${report.date_to}.csv`}
          />
        </>
      )}
    </div>
  );
}
