import Link from "next/link";

import ReportDownloadButton from "@/components/ReportDownloadButton";
import {
  FIGURES, PERFORMANCE_PATH, csvFilename, csvUrl, formatFigure, periodHref, type Performance, type PerformanceParams,
} from "@/lib/recruiterPerformance";

const FIELD = { display: "grid", gap: 4 } as const;

// rec-033 (EVID-018 §24, DEC-SCOPE-181): the period's fifteen figures as tiles (the Total, or the recruiter drilled into) and, for the
// whole scope, the same figures per recruiter with the Total as the footer (AC2). The period is a plain GET form, so a view can be shared
// and needs no client JS; it is keyed and `autoComplete="off"` so a client navigation or Chrome's form restore never shows stale dates.
export default function RecruiterPerformancePanel({ data, error, params, today }: {
  data: Performance | null; error?: string; params: PerformanceParams; today: string;
}) {
  const from = data?.date_from ?? params.from ?? "";
  const to = data?.date_to ?? params.to ?? "";
  const recruiter = data?.recruiter ?? null;
  const people = data?.items.filter((row) => row.user_id !== null) ?? [];
  const title = recruiter ? `${recruiter.full_name}'s figures` : "Team figures";
  return (
    <section className="card" aria-labelledby="performance-title" style={{ marginTop: 16 }}>
      <h3 id="performance-title">{title}</h3>
      <form key={`${from}|${to}|${params.recruiter ?? ""}`} method="get" action={PERFORMANCE_PATH} autoComplete="off" aria-label="Period"
        style={{ display: "flex", flexWrap: "wrap", alignItems: "end", gap: 8, margin: "8px 0 12px" }}>
        <div style={FIELD}>
          <label htmlFor="performance-from">From</label>
          <input id="performance-from" className="input" type="date" name="from" defaultValue={from} max={today} />
        </div>
        <div style={FIELD}>
          <label htmlFor="performance-to">To</label>
          <input id="performance-to" className="input" type="date" name="to" defaultValue={to} max={today} />
        </div>
        {params.recruiter && <input type="hidden" name="recruiter" value={params.recruiter} />}
        <button className="btn secondary small" type="submit">Show</button>
      </form>
      {params.recruiter && <p><Link href={periodHref(from, to)}>All recruiters</Link></p>}
      {data === null ? (
        <p className="muted" role="alert">{error}</p>
      ) : (
        <>
          <ul className="metric-grid tel-tiles" aria-label={title}>
            {FIGURES.map((f) => (
              <li key={f.key} className="metric">
                <span>{f.label}</span>
                <strong>{formatFigure(data.totals[f.key], f.kind)}</strong>
                <small>{f.hint}</small>
              </li>
            ))}
          </ul>
          {!recruiter && (people.length === 0 ? (
            <p className="muted" role="status">No recruiters to compare yet. Unassigned companies and requirements still count in the Total.</p>
          ) : (
            <div className="table-wrap" role="region" aria-label="Performance by recruiter" tabIndex={0}>
              <table className="table">
                <caption className="visually-hidden">Performance by recruiter from {data.date_from} to {data.date_to}; select a name to see that recruiter alone</caption>
                <thead>
                  <tr>
                    <th scope="col">Recruiter</th>
                    {FIGURES.map((f) => <th key={f.key} scope="col">{f.label}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((row) => (
                    <tr key={row.user_id ?? "unassigned"}>
                      <th scope="row">
                        {row.user_id ? <Link href={periodHref(from, to, row.user_id)}>{row.full_name}</Link> : row.full_name}
                        {!row.active && <>{" "}<span className="badge">Inactive</span></>}
                      </th>
                      {FIGURES.map((f) => <td key={f.key}>{formatFigure(row[f.key], f.kind)}</td>)}
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr>
                    <th scope="row">Total</th>
                    {FIGURES.map((f) => <td key={f.key}>{formatFigure(data.totals[f.key], f.kind)}</td>)}
                  </tr>
                </tfoot>
              </table>
            </div>
          ))}
          <div style={{ marginTop: 16 }}>{/* QA33-02: not flush against the table */}
            <ReportDownloadButton url={csvUrl(data)} label="Download CSV" filename={csvFilename(data)} contentType="text/csv" busyLabel="Preparing CSV…" />
          </div>
        </>
      )}
    </section>
  );
}
