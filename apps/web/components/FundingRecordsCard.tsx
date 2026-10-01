import { serverApi } from "@/lib/api";
import { formatCalendarDate } from "@/lib/formatDate";
import { type FundingRecord, stageText, statusClass, SUPPORT_TYPE_LABEL } from "@/lib/fundingRecords";

// ENH-020 (spec §6, SCR-SCH-042): one student's funding support cases, read-only, for a linked parent, the coordinator or the
// principal. The host page fetches the cases in its own parallel read with `.catch(() => null)`, so `null` means "could not load"
// and never takes the rest of the page down. `headingLevel` follows the page: parent cards use h3, staff sections h2.
export default function FundingRecordsCard({ records, headingLevel = 3 }: { records: FundingRecord[] | null; headingLevel?: 2 | 3 }) {
  const Heading = headingLevel === 2 ? "h2" : "h3";
  return (
    <div className="card funding-card">
      <Heading>Funding support</Heading>
      {records === null ? (
        <p className="muted">Funding support cases couldn&apos;t be loaded. Reload the page to try again.</p>
      ) : records.length === 0 ? (
        <p className="muted">No funding support cases for this student.</p>
      ) : (
        records.map((r) => (
          <dl className="record-details" key={r.id}>
            <div className="record-details-row"><dt>Support type</dt><dd>{SUPPORT_TYPE_LABEL[r.support_type]}</dd></div>
            <div className="record-details-row"><dt>Stage</dt><dd><span className={statusClass(r.status)}>{stageText(r.status)}</span> since {formatCalendarDate(r.status_changed_on)}</dd></div>
            {r.provider_name && <div className="record-details-row"><dt>Provider</dt><dd>{r.provider_name}</dd></div>}
            {r.amount_text && <div className="record-details-row"><dt>Amount</dt><dd>{r.amount_text}</dd></div>}
            {r.closure_reason && <div className="record-details-row"><dt>Reason closed</dt><dd>{r.closure_reason}</dd></div>}
            {r.notes && <div className="record-details-row"><dt>Notes</dt><dd className="funding-notes">{r.notes}</dd></div>}
            {(r.updated_by_name || r.counselor_name) && <div className="record-details-row"><dt>Updated by</dt><dd>{r.updated_by_name || r.counselor_name}</dd></div>}
          </dl>
        ))
      )}
    </div>
  );
}

/** The read every host page joins into its own `Promise.all`; a failure becomes `null` (the card's "could not load" state). */
export async function loadFundingRecords(studentId: string): Promise<FundingRecord[] | null> {
  return serverApi<FundingRecord[]>(`/api/v1/school/students/${studentId}/funding-records`).catch(() => null);
}
