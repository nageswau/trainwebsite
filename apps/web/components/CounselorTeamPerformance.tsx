import Link from "next/link";

import { PerformanceFilters } from "@/components/CounselorPerformance";
import { SpreadsheetButtons } from "@/components/ExportButtons";
import {
  ADMIN_PERFORMANCE_API, ADMIN_PERFORMANCE_HOME, performanceUrl, type PerformanceQuery, type TeamFigures, type TeamPerformance,
} from "@/lib/counselorPerformance";
import { formatCalendarDate } from "@/lib/formatDate";
import { formatCount, formatPct } from "@/lib/managementCounseling";

function cell(row: TeamFigures, key: keyof TeamFigures) {
  const value = row[key];
  if (key === "conversion_pct") return value === null ? "—" : formatPct(value as number);
  return formatCount(value as number);
}

// ccrm-053 (DEC-SCOPE-323, PF7-PF9): every overseas counselor's figures for the Overseas Admin -- the filter form, one row per counselor
// (the name opens that counselor's own report with the same filters), the Total row, the definitions and the CSV / Excel of the screen.
export default function CounselorTeamPerformance({ data, error, query }: { data: TeamPerformance | null; error: string; query: PerformanceQuery }) {
  const period = { from: data?.from ?? query.from, to: data?.to ?? query.to };
  const applied: PerformanceQuery = { ...query, ...period };
  const figures = data?.columns.filter((c) => c.key !== "full_name") ?? [];
  return (
    <div className="action-card">
      {error && <p className="form-error" role="alert">{error}</p>}
      <PerformanceFilters home={ADMIN_PERFORMANCE_HOME} query={query} period={period} />
      {data && (
        <section>
          <h3 id="team-heading">Overseas counselors</h3>
          <p className="muted">
            {formatCalendarDate(data.from)} to {formatCalendarDate(data.to)}, India time (IST).
            {data.intake && ` Leads and applications for the ${data.intake} intake.`}
            {data.division && ` Leads in the ${data.division === "it" ? "IT" : "Overseas"} division.`} Applications, students and visas are as they stand today.
          </p>
          {data.items.length === 0 ? (
            <p className="empty" role="status">No overseas counselors yet.</p>
          ) : (
            <>
              <div className="table-scroll" role="region" aria-labelledby="team-heading" tabIndex={0}>
                <table className="table">
                  <caption className="visually-hidden">Overseas counselors&apos; performance</caption>
                  <thead>
                    <tr><th scope="col">Counselor</th>{figures.map((c) => <th key={c.key} scope="col">{c.label}</th>)}</tr>
                  </thead>
                  <tbody>
                    {data.items.map((r) => (
                      <tr key={r.id}>
                        <th scope="row">
                          <Link href={performanceUrl(applied, `${ADMIN_PERFORMANCE_HOME}/${r.id}`)}>{r.full_name}</Link>
                          {!r.active && <span className="muted"> (inactive)</span>}
                        </th>
                        {figures.map((c) => <td key={c.key}>{cell(r, c.key)}</td>)}
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr><th scope="row">Total</th>{figures.map((c) => <td key={c.key}><strong>{cell(data.totals, c.key)}</strong></td>)}</tr>
                  </tfoot>
                </table>
              </div>
              <SpreadsheetButtons csvUrl={performanceUrl(applied, `${ADMIN_PERFORMANCE_API}.csv`)} filename={`counselor-performance-${data.from}-to-${data.to}.csv`} label="Export counselor performance" />
            </>
          )}
          <dl className="metric-note">
            {data.columns.map((d) => (
              <div key={d.key}><dt style={{ display: "inline", fontWeight: 700 }}>{d.label}: </dt><dd style={{ display: "inline", margin: 0 }}>{d.definition}</dd></div>
            ))}
          </dl>
        </section>
      )}
    </div>
  );
}
