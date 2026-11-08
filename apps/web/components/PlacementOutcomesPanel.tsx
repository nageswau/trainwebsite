import Link from "next/link";

import { SpreadsheetButtons } from "@/components/ExportButtons";
import { PLACEMENTS_PATH } from "@/lib/placements";
import {
  GROUPS, OUTCOMES_PATH, drillHref, exportFilename, exportUrl, formatFigure, outcomeQuery, rateText, type OutcomeParams, type Outcomes,
} from "@/lib/placementOutcomes";

const FIELD = { display: "grid", gap: 4 } as const;
const HEADLINE = [
  { key: "placements", label: "Placements", hint: "Offers accepted in the period" },
  { key: "joined", label: "Joined", hint: "Of those placements" },
  { key: "joining_rate", label: "Joining rate", hint: "Joined ÷ (joined + did not join)" },
  { key: "time_to_fill_days", label: "Time to fill", hint: "Requirement opened → joined, average" },
  { key: "early_dropouts", label: "Early dropouts", hint: "Left inside the guarantee" },
  { key: "replacements_owed", label: "Replacements owed", hint: "Early dropouts not yet replaced" },
  { key: "client_rating", label: "Client satisfaction", hint: "Average rating out of 5" },
  { key: "candidate_rating", label: "Candidate satisfaction", hint: "Average rating out of 5" },
];
const REVENUE = [
  { key: "fee_generated", label: "Revenue generated", hint: "Expected fee of the joined placements" },
  { key: "invoiced", label: "Invoiced", hint: "Issued invoices, not cancelled" },
  { key: "collected", label: "Collected", hint: "Payments received on them" },
  { key: "outstanding", label: "Outstanding", hint: "Invoiced − collected" },
];

// pob-029 (DEC-SCOPE-438): the period's placement outcomes. The period, grouping and any drill-down filter are a plain GET form and
// links, so a view can be shared and needs no client JS. The totals, the group table and the placement list come from the same rows, so
// the table sums to the totals and the list is what the figures count.
export default function PlacementOutcomesPanel({ data, error, params, today }: { data: Outcomes | null; error?: string; params: OutcomeParams; today: string }) {
  const from = data?.date_from ?? params.from ?? "";
  const to = data?.date_to ?? params.to ?? "";
  const group = data?.group_by ?? params.group_by ?? "company";
  const filtered = Object.keys(data?.filters ?? {}).length > 0;
  return (
    <section className="card" aria-labelledby="outcomes-title" style={{ marginTop: 16 }}>
      <h3 id="outcomes-title">Outcomes</h3>
      <form key={`${from}|${to}|${group}`} method="get" action={OUTCOMES_PATH} autoComplete="off" aria-label="Report period and grouping"
        style={{ display: "flex", flexWrap: "wrap", alignItems: "end", gap: 8, margin: "8px 0 12px" }}>
        <div style={FIELD}>
          <label htmlFor="outcomes-from">From</label>
          <input id="outcomes-from" className="input" type="date" name="from" defaultValue={from} max={today} />
        </div>
        <div style={FIELD}>
          <label htmlFor="outcomes-to">To</label>
          <input id="outcomes-to" className="input" type="date" name="to" defaultValue={to} max={today} />
        </div>
        <div style={FIELD}>
          <label htmlFor="outcomes-group">Group by</label>
          <select id="outcomes-group" className="input" name="group_by" defaultValue={group}>
            {GROUPS.map((g) => <option key={g.key} value={g.key}>{g.label}</option>)}
          </select>
        </div>
        {Object.entries(data?.filters ?? {}).map(([key, value]) => <input key={key} type="hidden" name={key} value={value} />)}
        <button className="btn secondary small" type="submit">Show</button>
      </form>
      {filtered && <p><Link href={OUTCOMES_PATH + outcomeQuery({ from, to, group_by: group })}>Clear the drill-down filter</Link></p>}
      {data === null ? (
        <p className="muted" role="alert">{error}</p>
      ) : (
        <>
          <ul className="metric-grid tel-tiles money-tiles" aria-label="Placement outcomes">
            {[...HEADLINE, ...(data.revenue_visible ? REVENUE : [])].map((f) => (
              <li key={f.key} className="metric">
                <span>{f.label}</span>
                <strong>{formatFigure(f.key, data.totals[f.key])}</strong>
                <small>{f.hint}</small>
              </li>
            ))}
          </ul>
          {!data.revenue_visible && <p className="muted">Revenue figures need the client commercials permission.</p>}

          <h4 style={{ marginTop: 16 }}>Conversions</h4>
          <p className="muted">Counted in the period for the requirements you can see{filtered ? " (the company and vendor filters apply)" : ""}.</p>
          <ul className="metric-grid tel-tiles" aria-label="Conversions">
            <li className="metric"><span>Requirements</span><strong>{data.funnel.requirements}</strong><small>Opened</small></li>
            <li className="metric"><span>Submissions</span><strong>{data.funnel.submissions}</strong><small>{rateText(data.funnel.requirement_to_submission)} of requirements</small></li>
            <li className="metric"><span>Interviews</span><strong>{data.funnel.interviews}</strong><small>{rateText(data.funnel.submission_to_interview)} of submissions</small></li>
            <li className="metric"><span>Offers</span><strong>{data.funnel.offers}</strong><small>{rateText(data.funnel.interview_to_offer)} of interviews</small></li>
            <li className="metric"><span>Offer acceptance</span><strong>{rateText(data.funnel.offer_acceptance)}</strong><small>{data.funnel.offers_accepted} accepted, {data.funnel.offers_declined} declined</small></li>
          </ul>

          <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "center", gap: 8, marginTop: 16 }}>
            <h4 style={{ margin: 0 }}>By {data.group_label.toLowerCase()}</h4>
            {data.items.length > 0 && <SpreadsheetButtons csvUrl={exportUrl(data)} filename={exportFilename(data)} label="Export the outcome table" />}
          </div>
          {data.items.length === 0 ? (
            <p className="muted" role="status">No offers were accepted in this period.</p>
          ) : (
            <div className="table-wrap" role="region" aria-label={`Outcomes by ${data.group_label.toLowerCase()}`} tabIndex={0}>
              <table className="table">
                <caption className="visually-hidden">Placement outcomes by {data.group_label.toLowerCase()} from {data.date_from} to {data.date_to}</caption>
                <thead>
                  <tr>
                    <th scope="col">{data.group_label}</th>
                    {data.columns.map((c) => <th key={c.key} scope="col">{c.label}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((row) => {
                    const href = drillHref(data, row);
                    return (
                      <tr key={row.key ?? row.label}>
                        <th scope="row">{href ? <Link href={href}>{row.label}</Link> : row.label}</th>
                        {data.columns.map((c) => <td key={c.key}>{formatFigure(c.key, row.figures[c.key])}</td>)}
                      </tr>
                    );
                  })}
                </tbody>
                <tfoot>
                  <tr>
                    <th scope="row">Total</th>
                    {data.columns.map((c) => <td key={c.key}>{formatFigure(c.key, data.totals[c.key])}</td>)}
                  </tr>
                </tfoot>
              </table>
            </div>
          )}

          {data.placements_total > 0 && (
            <>
              <h4 style={{ marginTop: 16 }}>Placements behind these figures</h4>
              {data.placements_total > data.placements.length && (
                <p className="muted">Showing the newest {data.placements.length} of {data.placements_total}; the figures count all of them.</p>
              )}
              <div className="table-wrap" role="region" aria-label="Placements behind these figures" tabIndex={0}>
                <table className="table">
                  <thead>
                    <tr>
                      <th scope="col">Candidate</th><th scope="col">Requirement</th><th scope="col">Company</th><th scope="col">Status</th>
                      <th scope="col">Joined</th><th scope="col">Dropout</th><th scope="col">Ratings (client / candidate)</th>
                      {data.revenue_visible && <th scope="col">Fee</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {data.placements.map((p) => (
                      <tr key={p.id}>
                        <th scope="row"><Link href={`${PLACEMENTS_PATH}/${encodeURIComponent(p.id)}`}>{p.candidate.name}</Link> <span className="muted">{p.candidate.code}</span></th>
                        <td>{p.requirement.code} {p.requirement.title}</td>
                        <td>{p.company.name}{p.vendor ? ` via ${p.vendor.name}` : ""}</td>
                        <td>{p.status_label}</td>
                        <td>{p.joined_on ?? "—"}</td>
                        <td>{p.dropout_on ? `${p.dropout_on}${p.early_dropout ? " (early)" : ""}` : "—"}</td>
                        <td>{p.client_rating ?? "—"} / {p.candidate_rating ?? "—"}</td>
                        {data.revenue_visible && <td>{formatFigure("fee_generated", p.fee)}</td>}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}
    </section>
  );
}
