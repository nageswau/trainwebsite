import Link from "next/link";

import { formatCalendarDate } from "@/lib/formatDate";
import { AGENTS_HOME, type AgentCountKey, type AgentMoneyKey, type AgentsDashboard, type AgentsQuery } from "@/lib/managementAgents";
import { formatCount } from "@/lib/managementCounseling";
import { formatInr } from "@/lib/managementLedger";

const COUNTS: AgentCountKey[] = ["staff", "students", "applications", "offers", "visa", "enrollments"];
const MONEY: AgentMoneyKey[] = ["commission", "revenue"];
const isMoney = (key: string) => (MONEY as string[]).includes(key);
const value = (key: string, figure: number | string | null) => (figure === null ? "—" : isMoney(key) ? formatInr(figure as string) : formatCount(figure as number));

// mgmt-021 (EVID-017 §17, spec AN1-AN14): the period form, the twelve §17 figures, the Agent → … → Revenue chain and the agency ranking
// (the API's order, AN10) with an all-agency total. Server-rendered; a GET form, so refresh, back and shared links keep it. The super admin
// gets no money from the API, so the money tiles say whose figures they are and the money columns and the revenue step are left out.
export default function ManagementAgents({ data, error, query }: { data: AgentsDashboard | null; error: string; query: AgentsQuery }) {
  const period = { from: data?.from ?? query.from, to: data?.to ?? query.to };
  const columns = data ? [...COUNTS, ...(data.money_visible ? MONEY : [])] : [];
  const label = (key: string) => data?.figures.find((f) => f.key === key)?.label ?? key;
  const chainName = data?.chain.map((step) => step.label).join(" → ") ?? "";
  return (
    <div className="action-card">
      {error && <p className="form-error" role="alert">{error}</p>}
      <form key={`${period.from}-${period.to}`} method="get" action={AGENTS_HOME} aria-label="Choose a period" className="analytics-form" autoComplete="off">
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="agents-from">From</label>
          <input id="agents-from" className="input" type="date" name="from" defaultValue={period.from} required />
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="agents-to">To</label>
          <input id="agents-to" className="input" type="date" name="to" defaultValue={period.to} required />
        </div>
        <button className="btn" type="submit">Show</button>
        <Link className="btn secondary" href={AGENTS_HOME}>This month</Link>
      </form>
      {data && (
        <>
          <p className="muted">
            {formatCalendarDate(data.from)} to {formatCalendarDate(data.to)}, India time (IST). {data.totals.agents} {data.totals.agents === 1 ? "agency" : "agencies"}.
            Every figure is counted live from the EduSphere records.
          </p>
          <section>
            <h3>Agent network</h3>
            <ul className="metric-grid snapshot-tiles" aria-label="Agent network figures">
              {data.figures.map((f) => (
                <li key={f.key} className="metric">
                  <span>{f.label}</span>
                  {data.totals[f.key] === null ? <strong className="metric-untracked">Partners only</strong> : <strong>{value(f.key, data.totals[f.key])}</strong>}
                  <p className="metric-note">{f.definition}</p>
                </li>
              ))}
            </ul>
          </section>
          <section className="card" aria-labelledby="agents-chain">
            <h3 id="agents-chain">{chainName}</h3>
            <p className="muted">Which agents are genuinely producing business: each step is the network total for the period.</p>
            <ol className="funnel" aria-label={chainName}>
              {data.chain.map((step) => (
                <li className="funnel-row" key={step.key}>
                  <span className="funnel-label">{step.label}</span>
                  <span className="funnel-count">{value(step.key, step.value)}</span>
                </li>
              ))}
            </ol>
          </section>
          <section id="agencies" className="agents-ranking">
            <h3 id="agencies-heading">Agency-wise performance</h3>
            {data.agencies.length === 0 ? (
              <p className="empty" role="status">No approved agencies yet.</p>
            ) : (
              <div className="table-scroll" role="region" aria-labelledby="agencies-heading" tabIndex={0}>
                <table className="table">
                  <caption className="visually-hidden">Agency-wise performance</caption>
                  <thead>
                    <tr>
                      <th scope="col">Rank</th><th scope="col">Agency</th>
                      {columns.map((key) => <th key={key} scope="col">{label(key)}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {data.agencies.map((a, index) => (
                      <tr key={a.id}>
                        <td>{index + 1}</td>
                        <th scope="row" className="agents-agency">
                          {a.name}
                          <span className="muted agents-agency-meta">{[a.prefix, a.status === "suspended" && "Suspended", a.new && "New"].filter(Boolean).join(" · ")}</span>
                        </th>
                        {columns.map((key) => <td key={key}>{value(key, a[key])}</td>)}
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr>
                      <td />
                      <th scope="row">All agencies</th>
                      {columns.map((key) => <td key={key}><strong>{value(key, data.totals[key])}</strong></td>)}
                    </tr>
                  </tfoot>
                </table>
              </div>
            )}
            <p className="muted">
              Ranked by enrollments, then applications, then students.{" "}
              {data.money_visible && "University commission is received per university, so it is not part of an agency's revenue."}
            </p>
          </section>
        </>
      )}
    </div>
  );
}
