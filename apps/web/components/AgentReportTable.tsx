import type { Ref } from "react";

import type { AgentReport, AgentReportCell } from "@/lib/types";

// AGN-020 (DEC-SCOPE-063; spec §6.2): one report as a table -- presentation only. The columns come from the server, so the screen and
// the CSV share their labels. On a phone the table stacks into labelled blocks (QA18-04 `stack`); the first column is the row header.
// Values are text nodes only. A summary's Total row is the footer; a list gets a pager (Previous/Next, `aria-disabled` at the ends).

function show(value: AgentReportCell | undefined): string {
  return value === null || value === undefined || value === "" ? "—" : String(value);
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const WIDE = 8; // QA20-06: more columns than this do not fit a laptop-width card (Applications has 11)

/** Numbers right-aligned; a date never breaks across lines ("2026-10-" / "03", QA20-06). */
function cellClass(numeric: boolean, value: AgentReportCell | undefined): string | undefined {
  if (numeric) return "num";
  return typeof value === "string" && ISO_DATE.test(value) ? "nowrap" : undefined;
}

export default function AgentReportTable({ report, headingId, caption, busy, onPage, regionRef }: {
  report: AgentReport;
  headingId: string;
  caption: string;
  busy: boolean;
  onPage: (offset: number) => void;
  regionRef?: Ref<HTMLDivElement>;
}) {
  const [first, ...rest] = report.columns;
  const row = (item: Record<string, AgentReportCell>) => (
    <>
      <th scope="row">{show(item[first.key])}</th>
      {rest.map((c) => (
        <td key={c.key} data-label={c.label} className={cellClass(c.numeric, item[c.key])}>{show(item[c.key])}</td>
      ))}
    </>
  );
  const list = report.totals === null;
  const start = report.total ? report.offset + 1 : 0;
  const end = Math.min(report.offset + report.items.length, report.total);
  const atStart = report.offset === 0;
  const atEnd = report.offset + report.limit >= report.total;

  return (
    <>
      {report.columns.length > WIDE && <p className="muted wide-hint">Scroll sideways to see every column.</p>}
      <div ref={regionRef} className={`table-scroll${busy ? " report-busy" : ""}`} tabIndex={0} role="region" aria-labelledby={headingId} aria-busy={busy}>
        <table className="table compact stack">
          <caption className="visually-hidden">{caption}</caption>
          <thead>
            <tr>{report.columns.map((c) => <th key={c.key} scope="col" className={c.numeric ? "num" : undefined}>{c.label}</th>)}</tr>
          </thead>
          <tbody>
            {report.items.map((item, i) => <tr key={i}>{row(item)}</tr>)}
          </tbody>
          {report.totals && <tfoot><tr>{row(report.totals)}</tr></tfoot>}
        </table>
      </div>
      {list && report.total > 0 && (
        <div className="pager">
          <span role="status">{`Showing ${start}–${end} of ${report.total}`}</span>
          <button type="button" className="btn small" aria-disabled={atStart} onClick={() => !atStart && onPage(Math.max(0, report.offset - report.limit))}>Previous</button>
          <button type="button" className="btn small" aria-disabled={atEnd} onClick={() => !atEnd && onPage(report.offset + report.limit)}>Next</button>
        </div>
      )}
    </>
  );
}
