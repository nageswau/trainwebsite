import Link from "next/link";

import { formatCalendarDate } from "@/lib/formatDate";
import { BDM_DASHBOARD_HOME, BDM_DASHBOARD_TYPES, bdmDashboardHref, type BdmDashboard, type BdmDashboardFigure, type BdmDashboardQuery } from "@/lib/managementBdm";

function Tiles({ label, figures }: { label: string; figures: BdmDashboardFigure[] }) {
  if (figures.length === 0) return null;
  return (
    <section>
      <h3>{label}</h3>
      <ul className="metric-grid snapshot-tiles" aria-label={label}>
        {figures.map((f) => (
          <li key={f.key} className="metric">
            <span>{f.label}</span>
            {f.value === null ? <strong className="metric-untracked">Not tracked</strong> : <strong>{f.value.toLocaleString("en-IN")}</strong>}
            <p className="metric-note">{f.definition}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}

// mgmt-020 (EVID-017 §16, spec BD1-BD12): one tab per BDM type (links, so refresh, back and shared links keep the type and period), the
// bdm-024 period form, and the type's figures split into the chosen period and right now. Server-rendered.
export default function ManagementBdm({ data, error, query }: { data: BdmDashboard | null; error: string; query: BdmDashboardQuery }) {
  const period = { from: data?.from ?? query.from, to: data?.to ?? query.to };
  return (
    <div className="action-card">
      <nav aria-label="BDM types" className="report-tablist wrap">
        {BDM_DASHBOARD_TYPES.map(({ type, label }) => (
          <Link key={type} href={bdmDashboardHref(query, type)} className="s360-tab" aria-current={type === query.type ? "page" : undefined}>
            {label}
          </Link>
        ))}
      </nav>
      {error && <p className="form-error" role="alert">{error}</p>}
      <form key={`${query.type}-${period.from}-${period.to}`} method="get" action={BDM_DASHBOARD_HOME} aria-label="Choose a period" className="analytics-form" autoComplete="off">
        <input type="hidden" name="type" value={query.type} />
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="bdm-dashboard-from">From</label>
          <input id="bdm-dashboard-from" className="input" type="date" name="from" defaultValue={period.from} required />
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="bdm-dashboard-to">To</label>
          <input id="bdm-dashboard-to" className="input" type="date" name="to" defaultValue={period.to} required />
        </div>
        <button className="btn" type="submit">Show</button>
        <Link className="btn secondary" href={bdmDashboardHref({ type: query.type, from: "", to: "" }, query.type)}>This month</Link>
      </form>
      {data && (
        <>
          <p className="muted">
            {formatCalendarDate(data.from)} to {formatCalendarDate(data.to)}, India time (IST). {data.bdm_count} active {data.label}{data.bdm_count === 1 ? "" : "s"}. Every
            figure covers all BDM teams and is counted live from the EduSphere records.
          </p>
          <Tiles label="In the period" figures={data.figures.filter((f) => f.basis === "period")} />
          <Tiles label="Right now" figures={data.figures.filter((f) => f.basis === "now")} />
        </>
      )}
    </div>
  );
}
