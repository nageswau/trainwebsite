import Link from "next/link";

import {
  COMPARISON_GROUPS, COMPARISON_PATH, comparisonHref, type Comparison, type ComparisonKey, type ComparisonRow,
} from "@/lib/recruiterComparison";
import type { PerformanceParams } from "@/lib/recruiterPerformance";
import { inr } from "@/lib/recruiterRevenue";

const FIELD = { display: "grid", gap: 4 } as const;
const FIGURES = COMPARISON_GROUPS.flatMap((group): readonly { key: ComparisonKey; label: string }[] => group.figures);

const STARTS = new Set<ComparisonKey>(COMPARISON_GROUPS.map((group) => group.figures[0].key)); // QA34-03: each group's first column
const start = (key: ComparisonKey) => (STARTS.has(key) ? "group-start" : undefined);

const value = (row: ComparisonRow, key: ComparisonKey) => (key === "revenue" ? inr(row.revenue) : row[key].toLocaleString("en-IN"));
const cells = (row: ComparisonRow) => FIGURES.map((f) => <td key={f.key} className={start(f.key)}>{value(row, f.key)}</td>);

// rec-034 (EVID-018 §25, DEC-SCOPE-183): the twelve business-development and recruitment figures per recruiter, side by side, with the
// Total as the footer (BP4). A recruiter sees only their own row (`own`: no names to open, no Total). The period form is rec-033's plain
// GET form, keyed and `autoComplete="off"` so a client navigation or Chrome's form restore never shows stale dates.
export default function RecruiterComparisonPanel({ data, error, params, today, own }: {
  data: Comparison | null; error?: string; params: PerformanceParams; today: string; own: boolean;
}) {
  const from = data?.date_from ?? params.from ?? "";
  const to = data?.date_to ?? params.to ?? "";
  const narrowed = !own && data?.recruiter ? data.recruiter : null;
  const title = own ? "Your figures" : narrowed ? `${narrowed.full_name}'s figures` : "Team figures";
  return (
    <section className="card" aria-labelledby="comparison-title" style={{ marginTop: 16 }}>
      <h3 id="comparison-title">{title}</h3>
      <form key={`${from}|${to}|${params.recruiter ?? ""}`} method="get" action={COMPARISON_PATH} autoComplete="off" aria-label="Period"
        style={{ display: "flex", flexWrap: "wrap", alignItems: "end", gap: 8, margin: "8px 0 12px" }}>
        <div style={FIELD}>
          <label htmlFor="comparison-from">From</label>
          <input id="comparison-from" className="input" type="date" name="from" defaultValue={from} max={today} />
        </div>
        <div style={FIELD}>
          <label htmlFor="comparison-to">To</label>
          <input id="comparison-to" className="input" type="date" name="to" defaultValue={to} max={today} />
        </div>
        {params.recruiter && !own && <input type="hidden" name="recruiter" value={params.recruiter} />}
        <button className="btn secondary small" type="submit">Show</button>
      </form>
      {!own && params.recruiter && <p><Link href={comparisonHref(from, to)}>All recruiters</Link></p>}{/* QA34-01: also after a 404 */}
      {data === null ? (
        <p className="muted" role="alert">{error}</p>
      ) : data.items.length === 0 ? (
        <p className="muted" role="status">No recruiters to compare yet. Figures appear here once your team logs work in the period.</p>
      ) : (
        <div className="table-wrap" role="region" aria-label="Performance by recruiter" tabIndex={0}>
          <table className="table">
            <caption className="visually-hidden">
              Business development and recruitment by recruiter from {data.date_from} to {data.date_to}, each figure credited to whoever did the work
            </caption>
            <thead>
              <tr>
                <td />
                {COMPARISON_GROUPS.map((group) => (
                  <th key={group.label} scope="colgroup" colSpan={group.figures.length} className="group-start">{group.label}</th>
                ))}
              </tr>
              <tr>
                <th scope="col">Recruiter</th>
                {FIGURES.map((f) => <th key={f.key} scope="col" className={start(f.key)}>{f.label}</th>)}
              </tr>
            </thead>
            <tbody>
              {data.items.map((row) => (
                <tr key={row.user_id ?? row.full_name}>
                  <th scope="row">
                    {own || narrowed || !row.user_id ? row.full_name : <Link href={comparisonHref(from, to, row.user_id)}>{row.full_name}</Link>}
                    {!row.active && <>{" "}<span className="badge">Inactive</span></>}
                  </th>
                  {cells(row)}
                </tr>
              ))}
            </tbody>
            {data.totals && !own && !narrowed && (
              <tfoot>
                <tr>
                  <th scope="row">Total</th>
                  {cells(data.totals)}
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      )}
    </section>
  );
}
