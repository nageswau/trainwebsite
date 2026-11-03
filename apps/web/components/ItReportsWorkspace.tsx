import Link from "next/link";

import ReportDownloadButton from "@/components/ReportDownloadButton";
import {
  GROUP_COLUMNS, IT_REPORTS, ROW_COLUMNS, itReportExportUrl, itReportHref, itReportTotals,
  type ItColumn, type ItReport, type ItReportPage, type ItReportParams, type ItReportRow,
} from "@/lib/itReports";

const EMPTY = "Nothing matches these filters.";

function Table({ label, caption, columns, rows, action }: {
  label: string; caption?: string; columns: ItColumn[]; rows: ItReportRow[]; action?: (row: ItReportRow) => React.ReactNode;
}) {
  return (
    <div className="table-scroll" tabIndex={0} role="region" aria-label={label}>
      <table className="table compact stack">
        <caption className={caption ? undefined : "visually-hidden"}>{caption ?? label}</caption>
        <thead>
          <tr>
            {columns.map((c) => <th key={c.key} scope="col" className={c.num ? "num" : undefined}>{c.label}</th>)}
            {action && <th scope="col"><span className="visually-hidden">Rows</span></th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              <th scope="row">{columns[0].show(row[columns[0].key])}</th>
              {columns.slice(1).map((c) => <td key={c.key} data-label={c.label} className={c.num ? "num" : undefined}>{c.show(row[c.key])}</td>)}
              {action && <td data-label="Rows">{action(row)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// itc-032 (DEC-SCOPE-369): the management IT reports -- a strip of report links (each report is its own address), one GET filter form with
// the same five filters on every tab (no client JS), the totals, what each figure means, the groups (each course or staff row links to the
// rows behind it: the drill-down), the page of rows and its CSV. `page` null + `error` = the read failed or the API refused the filters
// (422 text shown above the form, which keeps the inputs). On a phone the tables stack into labelled blocks (`.table.stack`).
export default function ItReportsWorkspace({ report, tabs, page, error, params, basePath }: {
  report: ItReport; tabs: { key: ItReport; label: string }[]; page: ItReportPage | null; error: string; params: ItReportParams; basePath: string;
}) {
  const label = tabs.find((t) => t.key === report)?.label ?? report;
  const about = IT_REPORTS.find((t) => t.key === report)?.about;
  const select = (name: keyof ItReportParams, text: string, all: string, choices: { value: string; label: string }[]) => (
    <div className="field" style={{ margin: 0 }}>
      <label htmlFor={`it-reports-${name}`}>{text}</label>
      <select id={`it-reports-${name}`} name={name} defaultValue={String(params[name] ?? "")}>
        <option value="">{all}</option>
        {/* A value from the address that is not offered (refused with a 422) stays visible beside the message. */}
        {params[name] && !choices.some((c) => c.value === params[name]) && <option value={String(params[name])}>{String(params[name])}</option>}
        {choices.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
      </select>
    </div>
  );
  const o = page?.options;
  // Without client JS the batch list cannot follow the course box live: once a course is applied, only its batches are offered.
  const batches = (o?.batches ?? []).filter((b) => !params.program_id || b.program_id === params.program_id).map((b) => ({ value: b.id, label: b.name }));
  const dates = { date_from: params.date_from ?? page?.filters.date_from ?? "", date_to: params.date_to ?? page?.filters.date_to ?? "" };
  const drill = (row: ItReportRow) => {
    const narrowed = report === "activity" ? { owner_id: row.owner_id } : { program_id: row.program_id };
    const value = Object.values(narrowed)[0];
    if (typeof value !== "string") return null;
    return <Link href={itReportHref(basePath, report, { ...params, ...narrowed } as ItReportParams, report)}>Show rows<span className="visually-hidden"> for {String(row[GROUP_COLUMNS[report][0].key])}</span></Link>;
  };
  const byStage = page && report === "funnel" ? (page.totals.by_stage as { stage: string; label: string; count: number }[]) : [];

  return (
    <div className="action-card agent-reports">
      <nav aria-label="IT reports" className="report-tablist wrap">
        {tabs.map((t) => (
          <Link key={t.key} className="s360-tab" href={itReportHref(basePath, t.key, params, report)} aria-current={t.key === report ? "page" : undefined}>{t.label}</Link>
        ))}
      </nav>
      <h3>{label}</h3>
      {about && <p className="muted">{about}</p>}
      {error && <p className="form-error" role="alert">{error}</p>}
      <form method="get" action={basePath} aria-label="Report filters" className="analytics-form">
        <input type="hidden" name="report" value={report} />
        {select("program_id", "Course", "All courses", (o?.courses ?? []).map((c) => ({ value: c.id, label: c.title })))}
        {select("batch_id", "Batch", "All batches", batches)}
        {select("owner_id", report === "activity" ? "Staff member" : "Owner", "Everyone", (o?.owners ?? []).map((p) => ({ value: p.id, label: p.name })))}
        {select("status", "Status", "Any status", o?.statuses ?? [])}
        {(["date_from", "date_to"] as const).map((name) => (
          <div className="field" style={{ margin: 0 }} key={name}>
            <label htmlFor={`it-reports-${name}`}>{name === "date_from" ? "From" : "To"}</label>
            <input id={`it-reports-${name}`} className="input" type="date" name={name} defaultValue={dates[name] ?? ""} />
          </div>
        ))}
        <button className="btn" type="submit">Apply</button>
        <Link className="btn secondary" href={`${basePath}?report=${report}`}>Clear filters</Link>
      </form>
      {page && (
        <>
          <dl className="kpi-grid dashboard-tiles" aria-label={`${label} totals`}>
            {itReportTotals(report, page.totals).map((t) => (
              <div className="kpi-tile" key={t.label}><dt>{t.label}</dt><dd className="kpi-value">{t.value}</dd></div>
            ))}
          </dl>
          <details className="muted" style={{ margin: "8px 0 12px" }}>
            <summary>What these figures mean</summary>
            <dl>
              {page.definitions.map((d) => (
                <div key={d.key}><dt style={{ fontWeight: 600 }}>{d.label}</dt><dd style={{ margin: "0 0 6px" }}>{d.definition}</dd></div>
              ))}
            </dl>
          </details>
          {byStage.length > 0 && (
            <Table label="Leads by stage" caption="Leads by stage now" columns={[{ key: "label", label: "Stage", show: (v) => String(v) }, { key: "count", label: "Leads", show: (v) => String(v), num: true }]} rows={byStage} />
          )}
          {page.groups.length > 0 && (
            <Table label={`${label} by ${report === "activity" ? "staff member" : "course"}`} caption={report === "activity" ? "By staff member" : report === "funnel" ? "By course and source" : "By course"}
              columns={GROUP_COLUMNS[report]} rows={page.groups} action={drill} />
          )}
          {page.items.length === 0 && <p className="empty" role="status">{EMPTY}</p>}
          {page.items.length > 0 && (
            <>
              <h4 style={{ marginTop: 16 }}>Rows ({page.total})</h4>
              <Table label={`${label} rows`} columns={ROW_COLUMNS[report]} rows={page.items} />
              {page.total > page.limit && (
                <nav aria-label={`${label} pages`} style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
                  <span className="muted" style={{ fontSize: 13 }}>Showing {page.offset + 1}–{page.offset + page.items.length} of {page.total}</span>
                  {page.offset > 0 && <Link className="btn secondary small" href={itReportHref(basePath, report, params, report, Math.max(0, page.offset - page.limit))}>Previous</Link>}
                  {page.offset + page.limit < page.total && <Link className="btn secondary small" href={itReportHref(basePath, report, params, report, page.offset + page.limit)}>Next</Link>}
                </nav>
              )}
              <ReportDownloadButton url={itReportExportUrl(report, params)} label="Download CSV" filename={`it-${report}.csv`} contentType="text/csv" busyLabel="Preparing CSV…"
                hint="The CSV holds every row that matches these filters, not just this page." />
            </>
          )}
        </>
      )}
    </div>
  );
}
