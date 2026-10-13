import Link from "next/link";

import { formatCalendarDate } from "@/lib/formatDate";
import { formatInr } from "@/lib/managementLedger";
import {
  RECRUITMENT_HOME,
  RECRUITMENT_KPIS,
  placementRateText,
  recruitmentHref,
  type Recruitment,
  type RecruitmentFilters,
  type RecruitmentKpis,
} from "@/lib/managementRecruitment";

function kpiText(key: keyof RecruitmentKpis, kpis: RecruitmentKpis): string {
  if (key === "placement_rate") return placementRateText(kpis.placement_rate);
  if (key === "revenue") return formatInr(kpis.revenue ?? "0");
  return kpis[key].toLocaleString("en-IN");
}

// mgmt-025 (EVID-017 §21, spec RC1-RC12): the company-wide Recruitment dashboard for the operational tier. Server-rendered; the period is a
// GET form. The figures are the Recruiter CRM's own (rec-033/035), so the totals equal the recruiter management dashboard's.
export default function ManagementRecruitment({ data, error, filters }: { data: Recruitment | null; error: string; filters: RecruitmentFilters }) {
  const kpis = RECRUITMENT_KPIS.filter((kpi) => kpi.key !== "revenue" || data?.revenue_visible);
  return (
    <>
      {error && <p className="form-error" role="alert">{error}</p>}
      {/* Keyed on the address, so a client navigation to another period (This month, Back) remounts the uncontrolled inputs; with no
          dates in the address the inputs show the period on screen. */}
      <form key={recruitmentHref(filters)} method="get" action={RECRUITMENT_HOME} aria-label="Recruitment period" className="funnel-filters" autoComplete="off">
        <div className="field">
          <label htmlFor="recruitment-from">From</label>
          <input id="recruitment-from" name="date_from" type="date" defaultValue={filters.date_from || data?.date_from} />
        </div>
        <div className="field">
          <label htmlFor="recruitment-to">To</label>
          <input id="recruitment-to" name="date_to" type="date" defaultValue={filters.date_to || data?.date_to} />
        </div>
        <div className="funnel-filter-actions">
          <button className="btn" type="submit">Apply</button>
          {(filters.date_from || filters.date_to) && <Link href={RECRUITMENT_HOME}>This month</Link>}
        </div>
      </form>
      {data && (
        <>
          <p className="muted">
            Interviews, selections, joining, new companies and the placement rate count {formatCalendarDate(data.date_from)} to{" "}
            {formatCalendarDate(data.date_to)} (India time); the other figures are as of now. Placement rate is joining out of candidates sourced in
            the period.
            {!data.revenue_visible && " Revenue is shown to partners."}
          </p>
          <ul id="recruitment-kpis" className="metric-grid snapshot-tiles" aria-label="Recruiter KPIs">
            {kpis.map((kpi) => (
              <li key={kpi.key} className="metric">
                <span>{kpi.label}</span>
                <strong>{kpiText(kpi.key, data.kpis)}</strong>
              </li>
            ))}
          </ul>
          <section id="company-pipeline" className="card" aria-labelledby="recruitment-pipeline">
            <h3 id="recruitment-pipeline">Company pipeline</h3>
            <p className="muted">Companies in the Recruiter CRM by their current stage, now. Archived companies are left out.</p>
            <ol className="funnel" aria-label="Company pipeline">
              {data.pipeline.map((step) => (
                <li className="funnel-row" key={step.key}>
                  <span className="funnel-label">{step.label}</span>
                  <span className="funnel-count">{step.value.toLocaleString("en-IN")}</span>
                </li>
              ))}
            </ol>
            <p className="muted funnel-note">
              Requirement closed: {data.requirement_closed.toLocaleString("en-IN")} · Lost: {data.lost.toLocaleString("en-IN")}
            </p>
          </section>
        </>
      )}
    </>
  );
}
