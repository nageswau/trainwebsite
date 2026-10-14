import Link from "next/link";

import { formatCalendarDate } from "@/lib/formatDate";
import { formatCount } from "@/lib/managementCounseling";
import { FUNNEL_DIMENSIONS, FUNNEL_HOME, type FunnelBreakdown, type FunnelQuery, type FunnelStage, type StudentFunnel } from "@/lib/managementFunnel";

// The bar is decoration sized against the path's largest stage; the count is the text (GlobalEducationFunnel's pipeline-* styles).
const pct = (count: number, max: number) => (max > 0 ? Math.round((count / max) * 100) : 0);

function Path({ label, stages }: { label: string; stages: FunnelStage[] }) {
  const max = Math.max(0, ...stages.map((s) => s.value));
  return (
    <section className="funnel-path">
      <h3>{label}</h3>
      <ol className="pipeline-funnel" aria-label={label}>
        {stages.map((s) => (
          <li key={s.key} className="pipeline-stage">
            <span className="pipeline-label">{s.label}</span>
            <span className="pipeline-count">{formatCount(s.value)}</span>
            <span className="pipeline-track" aria-hidden="true"><span className="pipeline-fill" style={{ width: `${pct(s.value, max)}%` }} /></span>
            <span className="metric-note">{s.definition}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}

function Breakdown({ breakdown: b, stages, name }: { breakdown: FunnelBreakdown; stages: FunnelStage[]; name: (s: FunnelStage) => string }) {
  if (!b.tracked) return <p className="empty" role="status">{b.label} is not tracked in EduSphere yet, so the funnel cannot be broken down by it.</p>;
  const on = b.stages.map((key) => stages.find((s) => s.key === key)!);
  const others = stages.filter((s) => !b.stages.includes(s.key)).map(name);
  return (
    <>
      {b.rows.length === 0 && <p className="empty" role="status">No {b.label} recorded on anything in this period.</p>}
      <div className="table-scroll" role="region" aria-labelledby="breakdown-heading" tabIndex={0}>
        <table className="table">
          <caption className="visually-hidden">Student funnel by {b.label}</caption>
          <thead>
            <tr>
              <th scope="col">{b.label}</th>
              {on.map((s) => <th key={s.key} scope="col">{name(s)}</th>)}
            </tr>
          </thead>
          <tbody>
            {b.rows.map((r) => (
              <tr key={r.value}>
                <th scope="row">{r.label}</th>
                {on.map((s) => <td key={s.key}>{formatCount(r.counts[s.key] ?? 0)}</td>)}
              </tr>
            ))}
            <tr>
              <th scope="row">Unknown</th>
              {on.map((s) => <td key={s.key}>{formatCount(b.unknown[s.key] ?? 0)}</td>)}
            </tr>
          </tbody>
          <tfoot>
            <tr>
              <th scope="row">Total</th>
              {on.map((s) => <td key={s.key}>{formatCount(s.value)}</td>)}
            </tr>
          </tfoot>
        </table>
      </div>
      {others.length > 0 && <p className="muted">Not broken down by {b.label}: {others.join(", ")}. Their records carry no {b.label} value.</p>}
    </>
  );
}

// mgmt-016 (EVID-017 §11, spec SF1-SF16): the period and breakdown form, the lead journey, the IT and abroad paths side by side, and the
// breakdown table. Server-rendered; a GET form, so refresh, back and shared links keep the period and breakdown.
export default function ManagementFunnel({ data, error, query }: { data: StudentFunnel | null; error: string; query: FunnelQuery }) {
  const period = { from: data?.from ?? query.from, to: data?.to ?? query.to };
  const stages = data?.stages ?? [];
  const repeated = (s: FunnelStage) => stages.filter((t) => t.label === s.label).length > 1;
  const pathLabel = (key: string) => data?.paths.find((p) => p.key === key)?.label ?? key;
  const name = (s: FunnelStage) => (repeated(s) ? `${s.label} (${pathLabel(s.path)})` : s.label);
  const path = (key: string) => <Path label={pathLabel(key)} stages={stages.filter((s) => s.path === key)} />;
  return (
    <div className="action-card">
      {error && <p className="form-error" role="alert">{error}</p>}
      <form key={`${period.from}-${period.to}-${query.by}`} method="get" action={FUNNEL_HOME} aria-label="Choose a period and breakdown" className="analytics-form" autoComplete="off">
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="funnel-from">From</label>
          <input id="funnel-from" className="input" type="date" name="from" defaultValue={period.from} required />
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="funnel-to">To</label>
          <input id="funnel-to" className="input" type="date" name="to" defaultValue={period.to} required />
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="funnel-by">Break down by</label>
          <select id="funnel-by" className="input" name="by" defaultValue={query.by}>
            <option value="">No breakdown</option>
            {FUNNEL_DIMENSIONS.map((d) => <option key={d.key} value={d.key}>{d.key === "branch" ? `${d.label} (not tracked)` : d.label}</option>)}
          </select>
        </div>
        <button className="btn" type="submit">Show</button>
        <Link className="btn secondary" href={FUNNEL_HOME}>This month</Link>
      </form>
      {data && (
        <>
          <p className="muted">
            {formatCalendarDate(data.from)} to {formatCalendarDate(data.to)}, India time (IST). Each stage counts what reached it in the period, so a
            later stage can be larger than an earlier one: the stages are not one group of students followed through, and no conversion rate is shown.
          </p>
          {path("lead")}
          <div className="funnel-paths">
            {path("it")}
            {path("abroad")}
          </div>
          {data.breakdown && (
            <section>
              <h3 id="breakdown-heading">By {data.breakdown.label}</h3>
              <Breakdown breakdown={data.breakdown} stages={stages} name={name} />
            </section>
          )}
        </>
      )}
    </div>
  );
}
