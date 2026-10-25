import Link from "next/link";
import type { ReactNode } from "react";

import { hasCrmFilters, percentText, type CrmDefinition, type CrmFilterKey, type CrmFilters, type CrmReports } from "@/lib/managementCrmReports";

// The backlog's filters in its order (§13: no team filter, CC3): the query key, the label, the choices list and the "none" choice.
const SELECTS: { key: CrmFilterKey; label: string; options: keyof CrmReports["options"]; none?: string }[] = [
  { key: "counselor", label: "Counselor", options: "counselors", none: "No counselor" },
  { key: "country", label: "Destination", options: "countries" },
  { key: "university", label: "University", options: "universities" },
  { key: "course", label: "Course", options: "courses" },
  { key: "intake", label: "Intake", options: "intakes" },
];
const AGEING_BANDS = [["d0_7", "0–7 days"], ["d8_14", "8–14 days"], ["d15_30", "15–30 days"], ["d31_60", "31–60 days"], ["d61_plus", "Over 60 days"]] as const;

type Column<Row> = { key: string; label: string; cell: (row: Row) => ReactNode };

const count = (value: number) => value.toLocaleString("en-IN");
/** Columns that show one numeric field, labelled by the report's own definitions. */
function fields(definitions: CrmDefinition[], keys: string[], format: Record<string, (value: never) => string> = {}): Column<object>[] {
  return keys.map((key) => ({
    key,
    label: definitions.find((d) => d.key === key)?.label ?? key,
    cell: (row) => (format[key] ?? count)((row as Record<string, never>)[key]),
  }));
}

/** One report: its heading, how it is counted, and a table with a total row -- or its empty state. */
function Report<Total, Row extends Total>({ id, title, empty, rowHeader, firstColumn, definitions, rows, total, columns }: {
  id: string; title: string; empty: string; rowHeader: string; firstColumn: (row: Row) => string; definitions: CrmDefinition[];
  rows: Row[]; total: Total; columns: Column<Total>[];
}) {
  const heading = `${id}-heading`;
  return (
    <section className="card crm-report" aria-labelledby={heading}>
      <h3 id={heading}>{title}</h3>
      <details className="crm-definitions">
        <summary>How these are counted</summary>
        <dl>
          {definitions.map((d) => (
            <div key={d.key}>
              <dt>{d.label}</dt>
              <dd>{d.definition}</dd>
            </div>
          ))}
        </dl>
      </details>
      {rows.length === 0 ? (
        <p className="empty" role="status">{empty}</p>
      ) : (
        <div className="table-scroll" role="region" aria-labelledby={heading} tabIndex={0}>
          <table className="table" aria-labelledby={heading}>
            <thead>
              <tr>
                <th scope="col">{rowHeader}</th>
                {columns.map((c) => <th key={c.key} scope="col">{c.label}</th>)}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={firstColumn(row)}>
                  <th scope="row">{firstColumn(row)}</th>
                  {columns.map((c) => <td key={c.key}>{c.cell(row)}</td>)}
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <th scope="row">Total</th>
                {columns.map((c) => <td key={c.key}><strong>{c.cell(total)}</strong></td>)}
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </section>
  );
}

// ccrm-034 (DEC-SCOPE-267, R1-R10): the six management CRM reports, server-rendered; the filters are a GET form to `home`, the page
// that renders it (the Command Center or the Overseas Admin's), so refresh, back and shared links keep them.
export default function ManagementCrmReports({ data, error, filters, home }: { data: CrmReports | null; error: string; filters: CrmFilters; home: string }) {
  const percent = { offer_rate: percentText, conversion_pct: percentText } as Record<string, (value: never) => string>;
  return (
    <>
      {error && <p className="form-error" role="alert">{error}</p>}
      <form method="get" action={home} aria-label="Report filters" className="funnel-filters" autoComplete="off">
        <div className="field">
          <label htmlFor="crm-date-from">Created from</label>
          <input id="crm-date-from" name="date_from" type="date" defaultValue={filters.date_from} />
        </div>
        <div className="field">
          <label htmlFor="crm-date-to">Created to</label>
          <input id="crm-date-to" name="date_to" type="date" defaultValue={filters.date_to} />
        </div>
        {SELECTS.map((select) => (
          <div className="field" key={select.key}>
            <label htmlFor={`crm-${select.key}`}>{select.label}</label>
            <select id={`crm-${select.key}`} name={select.key} defaultValue={filters[select.key]}>
              <option value="">All</option>
              {select.none && <option value="none">{select.none}</option>}
              {(data?.options[select.options] ?? []).map((choice) => <option key={choice.value} value={choice.value}>{choice.label}</option>)}
            </select>
          </div>
        ))}
        <div className="funnel-filter-actions">
          <button className="btn" type="submit">Apply</button>
          {hasCrmFilters(filters) && <Link href={home}>Clear filters</Link>}
        </div>
      </form>
      {data && (
        <div className="crm-reports">
          <p className="muted">
            Figures as of {data.as_of}, counted live. Students and applications are counted separately: one student can have several applications.
          </p>
          <Report
            id="crm-ageing" title="Application ageing" empty="No open applications match these filters." rowHeader="Stage · sub-status"
            firstColumn={(r) => `${r.stage_label} · ${r.sub_status_label}`} definitions={data.ageing.definitions} rows={data.ageing.rows} total={data.ageing.total}
            columns={[
              ...fields(data.ageing.definitions, ["applications", "students"]),
              ...AGEING_BANDS.map(([key, label]) => ({ key, label, cell: (r: { bands: Record<string, number> }) => count(r.bands[key]) })),
              { key: "oldest_days", label: "Oldest (days)", cell: (r: { oldest_days: number | null }) => (r.oldest_days === null ? "—" : count(r.oldest_days)) },
            ]}
          />
          <Report
            id="crm-universities" title="University performance" empty="No applications match these filters." rowHeader="University"
            firstColumn={(r) => r.label} definitions={data.universities.definitions} rows={data.universities.rows} total={data.universities.total}
            columns={fields(data.universities.definitions, ["applications", "students", "offers", "offer_rate", "rejections", "acceptances", "enrollments"], percent)}
          />
          <Report
            id="crm-visa" title="Visa outcomes" empty="No visa cases match these filters." rowHeader="Destination"
            firstColumn={(r) => r.label} definitions={data.visa.definitions} rows={data.visa.rows} total={data.visa.total}
            columns={fields(data.visa.definitions, ["applications", "students", "submitted", "pending", "approved", "refused", "enrolled"])}
          />
          <Report
            id="crm-readiness" title="Document readiness" empty="No applications waiting for submission match these filters." rowHeader="Stage"
            firstColumn={(r) => r.stage_label} definitions={data.readiness.definitions} rows={data.readiness.rows} total={data.readiness.total}
            columns={fields(data.readiness.definitions, ["applications", "students", "ready", "blocked", "needs_override", "no_checklist"])}
          />
          <Report
            id="crm-leads" title="Lead conversion by intake" empty="No overseas leads match these filters." rowHeader="Intake"
            firstColumn={(r) => r.label} definitions={data.leads.definitions} rows={data.leads.rows} total={data.leads.total}
            columns={fields(data.leads.definitions, ["leads", "converted", "conversion_pct", "students", "applications"], percent)}
          />
          <Report
            id="crm-forecast" title="Forecast by intake" empty="No applications match these filters." rowHeader="Intake"
            firstColumn={(r) => r.label} definitions={data.forecast.definitions} rows={data.forecast.rows} total={data.forecast.total}
            columns={fields(data.forecast.definitions, ["applications", "students", "confirmed", "expected", "possible", "lost", "forecast"])}
          />
        </div>
      )}
    </>
  );
}
