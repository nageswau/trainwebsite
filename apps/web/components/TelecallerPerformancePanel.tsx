import Link from "next/link";

import ReportDownloadButton from "@/components/ReportDownloadButton";
import {
  COUNT_COLUMNS, PERFORMANCE_URL, TEAM_LABEL, ariaSort, csvFilename, nextDir, performanceQuery, sortHref,
  type Performance, type PerformanceParams, type SortKey,
} from "@/lib/telecallerPerformance";

const FIELD = { display: "grid", gap: 4 } as const;

// tel-023 (EVID-019 §16, DEC-SCOPE-109): Leads, Calls, Connected, Qualified, Appointments and Conversions per telecaller over a range.
// The range, team and sort are a plain GET form and header links, so it needs no client JS and a view can be shared. `activityBase`
// (PF1) is set only for viewers who may open a telecaller's daily activity; division admins see plain names.
export default function TelecallerPerformancePanel({ data, error, params, base, teams, today, activityBase }: {
  data: Performance | null; error?: string; params: PerformanceParams; base: string; teams: string[]; today: string; activityBase?: string;
}) {
  const shown = data ?? { date_from: params.date_from ?? "", date_to: params.date_to ?? "", team: params.team ?? null };
  return (
    <section className="card" aria-labelledby="performance-title" style={{ marginTop: 16 }}>
      <h3 id="performance-title">Telecaller performance</h3>
      <form method="get" action={base} style={{ display: "flex", flexWrap: "wrap", alignItems: "end", gap: 8, margin: "8px 0 12px" }}>
        {/* QA-02: explicit labels -- a select wrapped in its label is named after its options too ("Team All teams"). */}
        <div style={FIELD}>
          <label htmlFor="performance-from">From</label>
          <input id="performance-from" className="input" type="date" name="date_from" defaultValue={shown.date_from} max={today} />
        </div>
        <div style={FIELD}>
          <label htmlFor="performance-to">To</label>
          <input id="performance-to" className="input" type="date" name="date_to" defaultValue={shown.date_to} max={today} />
        </div>
        {teams.length > 1 && (
          <div style={FIELD}>
            <label htmlFor="performance-team">Team</label>
            <select id="performance-team" className="input" name="team" defaultValue={shown.team ?? ""}>
              <option value="">All teams</option>
              {teams.map((t) => <option key={t} value={t}>{TEAM_LABEL[t] ?? t}</option>)}
            </select>
          </div>
        )}
        {params.sort && <input type="hidden" name="sort" value={params.sort} />}
        {params.dir && <input type="hidden" name="dir" value={params.dir} />}
        <button className="btn secondary small" type="submit">Show</button>
      </form>
      {data === null ? (
        <p className="muted" role="alert">{error}</p>
      ) : data.items.length === 0 ? (
        <p className="empty" role="status">No telecallers in your scope yet.</p>
      ) : (
        <>
          <div className="table-wrap" role="region" aria-label="Performance by telecaller" tabIndex={0}>
            <table className="table">
              <caption className="visually-hidden">Performance from {data.date_from} to {data.date_to}, sorted by {data.sort} {data.dir === "asc" ? "ascending" : "descending"}</caption>
              <thead>
                <tr>
                  <SortHeader data={data} base={base} sortKey="name" label="Telecaller" />
                  <th scope="col">Team</th>
                  {COUNT_COLUMNS.map((c) => <SortHeader key={c.key} data={data} base={base} sortKey={c.key} label={c.label} />)}
                </tr>
              </thead>
              <tbody>
                {data.items.map((row) => (
                  <tr key={row.user_id}>
                    <th scope="row">
                      {activityBase ? <Link href={`${activityBase}/${row.user_id}/activity?date=${data.date_to}`}>{row.full_name}</Link> : row.full_name}
                      {!row.active && <>{" "}<span className="badge">Inactive</span></>}
                    </th>
                    <td>{row.team}</td>
                    {COUNT_COLUMNS.map((c) => <td key={c.key}>{row[c.key]}</td>)}
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <th scope="row">Total</th>
                  <td />
                  {COUNT_COLUMNS.map((c) => <td key={c.key}>{data.totals[c.key]}</td>)}
                </tr>
              </tfoot>
            </table>
          </div>
          <ReportDownloadButton
            url={`${PERFORMANCE_URL}.csv${performanceQuery({ date_from: data.date_from, date_to: data.date_to, team: data.team ?? undefined, sort: data.sort, dir: data.dir })}`}
            label="Download CSV" filename={csvFilename(data)} contentType="text/csv" busyLabel="Preparing CSV…"
          />
        </>
      )}
    </section>
  );
}

function SortHeader({ data, base, sortKey, label }: { data: Performance; base: string; sortKey: SortKey; label: string }) {
  const sorted = data.sort === sortKey;
  const next = nextDir(data, sortKey) === "asc" ? (sortKey === "name" ? "A to Z" : "lowest first") : sortKey === "name" ? "Z to A" : "highest first";
  return (
    <th scope="col" aria-sort={ariaSort(data, sortKey)}>
      <Link href={sortHref(base, data, sortKey)} aria-label={`${label}: sort ${next}`}>
        {label}
        <span aria-hidden="true">{sorted ? (data.dir === "asc" ? " ↑" : " ↓") : " ↕"}</span>
      </Link>
    </th>
  );
}
