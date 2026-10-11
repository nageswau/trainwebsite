import { MANAGEMENT_PATH, TOTALS, count, type Management, type ManagementParams } from "@/lib/recruiterManagement";

const FIELD = { display: "grid", gap: 4 } as const;
const LISTS = { display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fit, minmax(min(18rem, 100%), 1fr))", marginTop: 16 } as const;

// rec-035 (EVID-018 §26, DEC-SCOPE-183): the recruiter business on one card -- the seven totals as tiles, then the top companies by hires and the top
// job categories by open requirements. The period is a plain GET form (keyed, `autoComplete="off"`: rec-033's QA lessons), so a view can
// be shared and needs no client JS.
export default function RecruiterManagementPanel({ data, error, params, today }: {
  data: Management | null; error?: string; params: ManagementParams; today: string;
}) {
  const from = data?.date_from ?? params.from ?? "";
  const to = data?.date_to ?? params.to ?? "";
  return (
    <section className="card" aria-labelledby="business-title" style={{ marginTop: 16 }}>
      <h3 id="business-title">At a glance</h3>{/* QA35-01: not the page title again */}
      <form key={`${from}|${to}`} method="get" action={MANAGEMENT_PATH} autoComplete="off" aria-label="Period"
        style={{ display: "flex", flexWrap: "wrap", alignItems: "end", gap: 8, margin: "8px 0 12px" }}>
        <div style={FIELD}>
          <label htmlFor="business-from">From</label>
          <input id="business-from" className="input" type="date" name="from" defaultValue={from} max={today} />
        </div>
        <div style={FIELD}>
          <label htmlFor="business-to">To</label>
          <input id="business-to" className="input" type="date" name="to" defaultValue={to} max={today} />
        </div>
        <button className="btn secondary small" type="submit">Show</button>
      </form>
      {data === null ? (
        <p className="muted" role="alert">{error}</p>
      ) : (
        <>
          <ul className="metric-grid tel-tiles" aria-label="Recruiter business totals">
            {TOTALS.map((t) => (
              <li key={t.key} className="metric">
                <span>{t.label}</span>
                <strong>{count(data.totals[t.key])}</strong>
                <small>{t.hint}</small>
              </li>
            ))}
          </ul>
          <div style={LISTS}>
            <div>
              <h4 id="top-companies">Top Companies</h4>
              {data.top_companies.length === 0 ? (
                <p className="muted" role="status">No hires in this period yet.</p>
              ) : (
                <ol aria-labelledby="top-companies">
                  {data.top_companies.map((c) => <li key={c.id}>{c.name} – {count(c.joined)} {c.joined === 1 ? "hire" : "hires"}</li>)}
                </ol>
              )}
            </div>
            <div>
              <h4 id="top-categories">Top Job Categories</h4>
              {data.top_categories.length === 0 ? (
                <p className="muted" role="status">No open requirements with a job category.</p>
              ) : (
                <ol aria-labelledby="top-categories">
                  {data.top_categories.map((c) => (
                    <li key={c.id}>{c.name} – {count(c.open_requirements)} open {c.open_requirements === 1 ? "requirement" : "requirements"}</li>
                  ))}
                </ol>
              )}
            </div>
          </div>
        </>
      )}
    </section>
  );
}
