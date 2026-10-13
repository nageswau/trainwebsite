import Link from "next/link";

import { APPLICATIONS_HOME, hasFilters, shareText, stageShare, type ApplicationFunnel, type FunnelFilterKey, type FunnelFilters, type FunnelOptionKey } from "@/lib/managementApplications";

// The source's eight filters (§20) in its order: the query key, the source's word, the choices list and the "none" choice where one exists.
const SELECTS: { key: FunnelFilterKey; label: string; options: FunnelOptionKey; none?: string }[] = [
  { key: "agency", label: "Agent", options: "agencies", none: "No agency" },
  { key: "counselor", label: "Counselor", options: "counselors", none: "No counselor" },
  { key: "country", label: "Country", options: "countries" },
  { key: "university", label: "University", options: "universities" },
  { key: "course", label: "Course", options: "courses" },
  { key: "intake", label: "Intake", options: "intakes" },
  { key: "staff", label: "Staff", options: "staff" },
  { key: "status", label: "Status", options: "statuses" },
];

// mgmt-024 (EVID-017 §20, spec MF1-MF18): the application funnel for the operational tier. Server-rendered; the filters are a GET form.
// AGN-019's funnel styles: label and count as text, the share of Created as text, a decorative bar; a stage with no data reads "Not
// tracked" with no bar (M9), never 0.
export default function ManagementApplications({ data, error, filters }: { data: ApplicationFunnel | null; error: string; filters: FunnelFilters }) {
  const created = data?.stages.find((stage) => stage.key === "created")?.value ?? 0;
  return (
    <>
      {error && <p className="form-error" role="alert">{error}</p>}
      <form method="get" action={APPLICATIONS_HOME} aria-label="Application filters" className="funnel-filters" autoComplete="off">
        <div className="field">
          <label htmlFor="funnel-date-from">Created from</label>
          <input id="funnel-date-from" name="date_from" type="date" defaultValue={filters.date_from} />
        </div>
        <div className="field">
          <label htmlFor="funnel-date-to">Created to</label>
          <input id="funnel-date-to" name="date_to" type="date" defaultValue={filters.date_to} />
        </div>
        {SELECTS.map((select) => (
          <div className="field" key={select.key}>
            <label htmlFor={`funnel-${select.key}`}>{select.label}</label>
            <select id={`funnel-${select.key}`} name={select.key} defaultValue={filters[select.key]}>
              <option value="">All</option>
              {select.none && <option value="none">{select.none}</option>}
              {(data?.options[select.options] ?? []).map((choice) => (
                <option key={choice.value} value={choice.value}>{choice.label}</option>
              ))}
            </select>
          </div>
        ))}
        <div className="funnel-filter-actions">
          <button className="btn" type="submit">Apply</button>
          {hasFilters(filters) && <Link href={APPLICATIONS_HOME}>Clear filters</Link>}
        </div>
      </form>
      {data && (
        <section className="card" aria-labelledby="funnel-heading">
          <h3 id="funnel-heading">Funnel</h3>
          <p className="muted">
            Each stage counts the applications above that meet it today. Documents Complete means every document on the application is
            verified and no requested document is outstanding. Under Review, Accepted and CAS/COE are not recorded in EduSphere.
          </p>
          {created === 0 && <p className="empty" role="status">No applications match these filters.</p>}
          <ol className="funnel" aria-label="Application funnel">
            {data.stages.map((stage) => (
              <li className="funnel-row" key={stage.key}>
                <span className="funnel-label">{stage.label}</span>
                {stage.value === null ? (
                  <span className="funnel-count funnel-untracked">Not tracked</span>
                ) : (
                  <>
                    <span className="funnel-count">{stage.value.toLocaleString("en-IN")}</span>
                    {stage.key !== "created" && <span className="funnel-percent muted">{shareText(stage.value, created)}</span>}
                    <span className="funnel-track" aria-hidden="true">
                      {stage.value > 0 && <span className="funnel-fill" style={{ width: `${Math.max(2, stageShare(stage.value, created))}%` }} />}
                    </span>
                  </>
                )}
              </li>
            ))}
          </ol>
          {data.withdrawn > 0 && (
            <p className="muted funnel-note">
              {data.withdrawn.toLocaleString("en-IN")} of these applications are withdrawn; they are counted in Applications Created and in each
              stage they reached.
            </p>
          )}
        </section>
      )}
    </>
  );
}
