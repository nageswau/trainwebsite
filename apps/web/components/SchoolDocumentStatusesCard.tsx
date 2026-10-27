import { serverApi } from "@/lib/api";
import { COMPLETE } from "@/lib/applicationChecklist";
import { NEEDS_ACTION } from "@/lib/documentChecklists";

// nehn-039 (spec D2-D5, NEEDS_CONFIRMATION): one student's overseas document statuses for the four school roles -- statuses only,
// never files or notes; the financial class is left out by the API. The host page reads it in its own parallel read with
// `.catch(() => null)` (FundingRecordsCard's pattern), so `null` means "could not load" and never takes the page down.
export type SchoolDocumentStatus = { name: string; required: boolean; status: string; status_label: string };
export type SchoolDocumentStatuses = {
  student_id: string;
  applications: { application_id: string; university_name: string; has_checklist: boolean; items: SchoolDocumentStatus[] }[];
};

const tone = (status: string) => (COMPLETE.has(status) ? "status" : NEEDS_ACTION.has(status) ? "status error" : "status pending");

export default function SchoolDocumentStatusesCard({ data, headingLevel = 2 }: { data: SchoolDocumentStatuses | null; headingLevel?: 2 | 3 }) {
  const Heading = headingLevel === 2 ? "h2" : "h3";
  const Sub = headingLevel === 2 ? "h3" : "h4";
  return (
    <div className="card school-documents">
      <Heading>Overseas application documents</Heading>
      {data === null ? (
        <p className="muted">Document statuses couldn&apos;t be loaded. Reload the page to try again.</p>
      ) : data.applications.length === 0 ? (
        <p className="muted">No overseas applications linked yet.</p>
      ) : (
        <>
          <p className="muted">The status of each document the application needs. Financial documents are not shown.</p>
          {data.applications.map((a) => (
            <section key={a.application_id} style={{ marginTop: 12 }}>
              <Sub>{a.university_name}</Sub>
              {!a.has_checklist || a.items.length === 0 ? (
                <p className="muted">{a.has_checklist ? "No documents to show for this application." : "No document checklist yet for this application."}</p>
              ) : (
                <div className="table-wrap">
                  <table className="table stack compact">
                    <caption className="visually-hidden">Documents for {a.university_name}</caption>
                    <thead>
                      <tr><th scope="col">Document</th><th scope="col">Required</th><th scope="col">Status</th></tr>
                    </thead>
                    <tbody>
                      {a.items.map((item, i) => (
                        <tr key={i}>
                          <td data-label="Document">{item.name}</td>
                          <td data-label="Required">{item.required ? "Required" : "Optional"}</td>
                          <td data-label="Status"><span className={tone(item.status)}>{item.status_label}</span></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          ))}
        </>
      )}
    </div>
  );
}

/** The read every host page joins into its own `Promise.all`; a failure becomes `null` (the card's "could not load" state). */
export async function loadDocumentStatuses(studentId: string): Promise<SchoolDocumentStatuses | null> {
  return serverApi<SchoolDocumentStatuses>(`/api/v1/school/students/${studentId}/document-statuses`).catch(() => null);
}
