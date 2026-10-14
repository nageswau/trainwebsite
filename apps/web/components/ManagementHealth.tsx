import { formatMonth } from "@/lib/managementExpenses";
import { HEALTH_HOME, RAG_LABEL, measureText, type BusinessHealth, type HealthQuery, type HealthRag } from "@/lib/managementHealth";

// upc-028's pills: green, amber and red carry their word, so colour is never the only cue (BH9); a factor without data is neutral.
const PILL: Record<HealthRag, string> = { green: "status", amber: "status pending", red: "status error" };

function RagPill({ rag, empty }: { rag: HealthRag | null; empty: string }) {
  return rag ? <span className={PILL[rag]}>{RAG_LABEL[rag]}</span> : <span className="badge health-unknown">{empty}</span>;
}

// mgmt-030 (EVID-017 §30, spec BH1-BH14): "an instant understanding of the company" -- the overall score out of 100, one RAG line per
// factor, then the breakdown whose points add up to the score. Server-rendered; the month is a GET form, so refresh, back and shared
// links keep it. The API decides which factors a caller gets (super_admin: the operational six).
export default function ManagementHealth({ data, error, query, maxMonth }: { data: BusinessHealth | null; error: string; query: HealthQuery; maxMonth: string }) {
  const month = data?.month ?? query.month;
  const business = data?.scope !== "operational";
  return (
    <div className="action-card">
      {error && <p className="form-error" role="alert">{error}</p>}
      <form key={month} method="get" action={HEALTH_HOME} aria-label="Choose a month" className="analytics-form" autoComplete="off">
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="health-month">Month</label>
          <input id="health-month" className="input" type="month" name="month" defaultValue={month} max={maxMonth} min="2000-01" />
        </div>
        <button className="btn" type="submit">Show</button>
      </form>
      {data && (
        <>
          <p className="muted">
            {formatMonth(data.month)} compared with {formatMonth(data.previous_month)}.
            {data.partial && ` ${formatMonth(data.month)} is still running: it is scored so far, against the whole of ${formatMonth(data.previous_month)}.`}
            {!business && " Operational factors only: the finance factors are shown to partners only."}
          </p>
          <ul className="metric-grid snapshot-tiles health-overall" aria-label="Overall health">
            <li className="metric">
              <span>{business ? "Overall business health" : "Operational health"}</span>
              <strong>{data.score === null ? "—" : `${data.score}/100`}</strong>
              <RagPill rag={data.rag} empty="Not scored" />
            </li>
          </ul>
          {data.score === null && <p className="empty" role="status">Not enough data to score {formatMonth(data.month)}.</p>}
          <ul className="health-lines" aria-label="Health by factor">
            {data.factors.map((f) => (
              <li key={f.key}>
                {f.label}: <RagPill rag={f.rag} empty="Not available" />
              </li>
            ))}
          </ul>
          <h3 id="health-breakdown">Breakdown</h3>
          <div className="table-scroll" role="region" aria-labelledby="health-breakdown" tabIndex={0}>
            {/* QA30-02: `.table.stack` turns each factor into labelled lines on a phone (from each cell's data-label), so the points never
                sit off-screen; the band sits beside the score, and a factor that is not available gives its reason in Measure. */}
            <table className="table stack health-breakdown">
              <caption className="visually-hidden">Business health breakdown, {formatMonth(data.month)}</caption>
              <thead>
                <tr><th scope="col">Factor</th><th scope="col">Measure</th><th scope="col">Score</th><th scope="col">Weight</th><th scope="col">Points</th></tr>
              </thead>
              <tbody>
                {data.factors.map((f) => (
                  <tr key={f.key}>
                    <th scope="row">{f.label}</th>
                    <td data-label="Measure">{measureText(f)}</td>
                    <td data-label="Score" className="health-score">{f.score === null ? "—" : <span>{f.score} <RagPill rag={f.rag} empty="" /></span>}</td>
                    <td data-label="Weight">{f.weight}</td>
                    <td data-label="Points">{f.points ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
              {data.score !== null && (
                <tfoot>
                  <tr><th scope="row" colSpan={4}>Overall score</th><td>{data.score}</td></tr>
                </tfoot>
              )}
            </table>
          </div>
          <p className="muted" style={{ fontSize: 13 }}>
            Each factor is scored 0–100 against the month before: growth of 10% or more scores 100, no change 50, a fall of 10% or more 0.
            {/* QA30-01: the finance scales are explained only to the readers who see those factors (BH1). */}
            {business && " Profit is scored on the margin (0% → 40, 15% → 70, 30% → 100), Marketing ROI on the return (0% → 50, 100% → 100), and Expenses on how much faster or slower they grew than revenue."}
            {" "}The overall score is the weighted average; the points add up to it. A factor that is not available is left out and its weight shared out across
            the others. Green is 70 and above, Amber 40–69, Red below 40.
          </p>
        </>
      )}
    </div>
  );
}
