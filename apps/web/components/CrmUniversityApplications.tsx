import Link from "next/link";

import { ApiError } from "@/lib/api";
import {
  CRM_REPORTS_UNAVAILABLE, CRM_UNIVERSITY_NOT_FOUND, crmReportsHref, crmUniversityHref, type CrmFilters, type CrmUniversityApplications as Data,
} from "@/lib/managementCrmReports"; // prettier-ignore

/** The drill-down pages' message for a failed read other than 401/403 (those show the access card). */
export function crmUniversityError(e: unknown): string {
  if (!(e instanceof ApiError)) return CRM_REPORTS_UNAVAILABLE;
  return e.status === 404 ? CRM_UNIVERSITY_NOT_FOUND : e.status === 422 ? e.message : CRM_REPORTS_UNAVAILABLE;
}

const VISA = { approved: "Approved", refused: "Refused", pending: "Pending" } as const;
const COLUMNS = ["Application", "Student", "Course","Intake", "Stage", "Counselor", "Deposit paid", "Visa"];

// ccrm-052: the applications behind one university's row of the CRM university report, with the report's filters (kept on the way back)
// and one page of 100 at a time. Server-rendered, like the report.
export default function CrmUniversityApplications({ data, error, filters, home }: { data: Data | null; error: string; filters: CrmFilters; home: string }) {
  const heading = "crm-university-applications-heading";
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  return (
    <>
      <div className="portal-title">
        <div>
          <div className="eyebrow">
            <Link href={crmReportsHref(home, filters)}>← Back to CRM reports</Link>
          </div>
          <h2>{data?.university.label ?? "University applications"}</h2>
          {data && <p className="muted">{data.total === 1 ? "1 application" : `${data.total.toLocaleString("en-IN")} applications`} — the University performance row with these filters.</p>}
        </div>
      </div>
      {error && <p className="form-error" role="alert">{error}</p>}
      {data && (
        <section className="card crm-report" aria-labelledby={heading}>
          <h3 id={heading}>Applications at {data.university.label}</h3>
          {data.items.length === 0 ? (
            <p className="empty" role="status">No applications at this university match these filters.</p>
          ) : (
            <div className="table-scroll" role="region" aria-labelledby={heading} tabIndex={0}>
              <table className="table" aria-labelledby={heading}>
                <thead>
                  <tr>
                    {COLUMNS.map((c) => <th key={c} scope="col">{c}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((a) => (
                    <tr key={a.application_id}>
                      <th scope="row">{a.application_code}</th>
                      <td>{a.student_name ?? "—"}</td>
                      <td>{a.course ?? "—"}</td>
                      <td>{a.intake}</td>
                      <td>{a.stage_label}</td>
                      <td>{a.counselor ?? "Not assigned"}</td>
                      <td>{a.deposit_paid ? "Yes" : "No"}</td>
                      <td>{a.visa ? VISA[a.visa] : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {pages > 1 && (
            <nav className="pager" aria-label="Pages">
              {data.page > 1 && <Link href={crmUniversityHref(home, data.university.id, filters, data.page - 1)}>Previous</Link>}
              <span className="muted">Page {data.page} of {pages}</span>
              {data.page < pages && <Link href={crmUniversityHref(home, data.university.id, filters, data.page + 1)}>Next</Link>}
            </nav>
          )}
        </section>
      )}
    </>
  );
}
