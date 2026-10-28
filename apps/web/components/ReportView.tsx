import Link from "next/link";

import { SpreadsheetButtons } from "@/components/ExportButtons";
import {
  type CatalogueItem, type Choice, FILTER_LABELS, type Report, type ReportOptions, type ReportParams, type ReportRow, csvUrl, pageHref,
} from "@/lib/reports";

const DATES = new Set(["from", "to", "completion_from", "completion_to"]);
const PICKERS: Record<string, keyof ReportOptions> = {
  course_id: "courses", batch_id: "batches", trainer_id: "trainers", recruiter_id: "recruiters", status: "statuses",
};
const ALL: Record<string, string> = {
  course_id: "All courses", batch_id: "All batches", trainer_id: "All trainers", recruiter_id: "All recruiters", status: "All statuses",
};

const show = (value: ReportRow[string] | undefined) => (value === null || value === undefined || value === "" ? "—" : String(value));
// QA9-02: a number is right-aligned; an ISO day never breaks across lines.
const cellClass = (value: ReportRow[string] | undefined) =>
  typeof value === "number" ? "num" : typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) ? "nowrap" : undefined;
const today = () => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date());

// nehn-009 (DEC-SCOPE-303): the reports the caller may view, each its own address.
export function ReportLibraryList({ items, basePath }: { items: CatalogueItem[]; basePath: string }) {
  if (items.length === 0) return <p className="empty" role="status">No reports are available to you.</p>;
  return (
    <ul className="link-list">
      {items.map((item) => (
        <li key={item.id}>
          <span className="who">
            <strong><Link href={pageHref(basePath, item.id, {}, 1)}>{item.title}</Link></strong>
            <span>{item.description}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

// nehn-009 (DEC-SCOPE-303): one registered report -- a plain GET filter form built from the filters the report declares (no client JS),
// the table, a pager and the CSV/Excel downloads of every matching row. Columns, labels and options are the server's. On a phone the
// table stacks into labelled blocks (`.table.stack`). `report` null + `error`: the read failed or the API refused the inputs; the form
// stays so the inputs can be corrected. `item.can_download` false drops the downloads (the API refuses them anyway).
export default function ReportView({ item, report, error, params, basePath }: {
  item: CatalogueItem; report: Report | null; error: string; params: ReportParams; basePath: string;
}) {
  const field = (name: string) => {
    const id = `report-${name}`;
    const label = <label htmlFor={id}>{FILTER_LABELS[name] ?? name}</label>;
    const value = params[name] ?? "";
    if (DATES.has(name)) return <>{label}<input id={id} className="input" type="date" name={name} defaultValue={value} /></>;
    if (name === "student") return <>{label}<input id={id} className="input" type="search" name={name} maxLength={100} defaultValue={value} placeholder="Code, name or email" /></>;
    if (name === "latest") return <>{label}<input id={id} className="input" type="number" name={name} min={1} max={1000} step={1} defaultValue={value} /></>;
    if (name === "attendance_below") return <>{label}<input id={id} className="input" type="number" name={name} min={1} max={100} step={1} defaultValue={value} /></>;
    const choices: Choice[] = report?.options[PICKERS[name]] ?? [];
    return (
      <>
        {label}
        <select id={id} name={name} defaultValue={value}>
          <option value="">{ALL[name] ?? "All"}</option>
          {/* A value from the address that is not offered stays visible beside the message. */}
          {value && !choices.some((c) => c.value === value) && <option value={value}>{value}</option>}
          {choices.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
        </select>
      </>
    );
  };
  const [first, ...rest] = report?.columns ?? [];
  const from = report ? (report.page - 1) * report.page_size : 0;
  const pages = report ? Math.ceil(report.total / report.page_size) : 0;
  const applied = Object.keys(params).filter((key) => key !== "page").length;

  return (
    <div className="action-card agent-reports">
      <h3>{item.title}</h3>
      <p className="muted">{item.description}</p>
      {error && <p className="form-error" role="alert">{error}</p>}
      {/* `key` + autoComplete off: Back after Apply shows the address's values, not ones the browser remembered (upc-031). noValidate:
          the API's own message names the field instead of the browser's bubble. */}
      {/* QA9-03: the filters fold away until one is applied (or refused), so the rows sit near the top on a phone -- the upc-025 map's
          `.map-filters` disclosure. */}
      <details className="map-filters" open={applied > 0 || Boolean(error)}>
        <summary>{applied ? `Filters (${applied} applied)` : "Filters"}</summary>
        <form key={JSON.stringify(params)} method="get" action={basePath} aria-label="Report filters" className="analytics-form" autoComplete="off" noValidate>
          <input type="hidden" name="report" value={item.id} />
          {Object.keys(FILTER_LABELS).filter((name) => item.filters.includes(name)).map((name) => (
            <div className="field" style={{ margin: 0 }} key={name}>{field(name)}</div>
          ))}
          <button className="btn" type="submit">Apply</button>
          <Link className="btn secondary" href={pageHref(basePath, item.id, {}, 1)}>Clear filters</Link>
        </form>
      </details>
      {/* QA9-01: past the last page is not "no match". */}
      {report && report.items.length === 0 && report.total > 0 && (
        <p className="empty" role="status">This page is past the last row. <Link href={pageHref(basePath, item.id, params, 1)}>Go to the first page</Link></p>
      )}
      {report && report.items.length === 0 && report.total === 0 && <p className="empty" role="status">No rows match these filters.</p>}
      {report && report.items.length > 0 && (
        <>
          <div className="table-scroll" tabIndex={0} role="region" aria-label={report.title}>
            <table className="table compact stack">
              <caption className="visually-hidden">{report.title}</caption>
              <thead><tr>{report.columns.map((c) => <th key={c.key} scope="col">{c.label}</th>)}</tr></thead>
              <tbody>
                {report.items.map((row, i) => (
                  <tr key={i}>
                    <th scope="row">{show(row[first.key])}</th>
                    {rest.map((c) => <td key={c.key} data-label={c.label} className={cellClass(row[c.key])}>{show(row[c.key])}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <nav aria-label="Report pages" className="pager">
            <span className="muted">{`Showing ${from + 1}–${from + report.items.length} of ${report.total}`}</span>
            {report.page > 1 && <Link className="btn secondary small" aria-label="Previous page" href={pageHref(basePath, item.id, params, report.page - 1)}>Previous</Link>}
            {report.page < pages && <Link className="btn secondary small" aria-label="Next page" href={pageHref(basePath, item.id, params, report.page + 1)}>Next</Link>}
          </nav>
          {item.can_download && (
            <SpreadsheetButtons csvUrl={csvUrl(item.id, params)} label={`Export ${report.title}`} filename={`${item.id}-${today()}.csv`}
              hint={`Downloads every matching row (${report.total.toLocaleString("en-IN")}), not only this page.`} />
          )}
        </>
      )}
    </div>
  );
}
