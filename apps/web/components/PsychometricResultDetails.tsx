import type { ReactNode } from "react";

import { formatCalendarDate } from "@/lib/formatDate";
import { hasResults, RESULT_LIST_FIELDS, type PsychometricResult } from "@/lib/psychometric";

// ENH-027 -- one psychometric result as structured data (spec §5.1). Presentational and server-safe; everything renders as text
// (React escaping), never HTML. Same `.record-details` list as ENH-026's CareerRecordDetails, so both records read alike in the
// 360° view and on the parent page. Empty fields are omitted.

export default function PsychometricResultDetails({ result }: { result: PsychometricResult }) {
  const rows: [string, ReactNode][] = [];
  if (result.test_date) rows.push(["Test date", formatCalendarDate(result.test_date)]);
  for (const { key, label } of RESULT_LIST_FIELDS) {
    const items = result[key];
    if (items?.length) rows.push([label, items.join(", ")]);
  }
  if (result.counsellor_remarks) rows.push(["Counsellor remarks", <span className="psy-result-text">{result.counsellor_remarks}</span>]);
  if (result.parent_discussion_on || result.parent_discussion_notes) {
    rows.push(["Parent discussion", (
      <>
        {result.parent_discussion_on ? formatCalendarDate(result.parent_discussion_on) : null}
        {result.parent_discussion_on && result.parent_discussion_notes ? " — " : null}
        {result.parent_discussion_notes ? <span className="psy-result-text">{result.parent_discussion_notes}</span> : null}
      </>
    )]);
  }
  if (result.follow_up_on) rows.push(["Follow-up", formatCalendarDate(result.follow_up_on)]);
  return (
    <dl className="record-details">
      {rows.map(([term, value]) => (
        <div key={term} className="record-details-row"><dt>{term}</dt><dd>{value}</dd></div>
      ))}
    </dl>
  );
}

export function PsychometricResultsList({ assessments }: { assessments: (PsychometricResult & { id: string; assessment_type: string })[] }) {
  if (assessments.length === 0) return null;
  return (
    <div className="psy-results">
      {assessments.map((a) => hasResults(a) ? (
        <details key={a.id} className="psy-result">
          <summary>{a.assessment_type} — results</summary>
          <PsychometricResultDetails result={a} />
        </details>
      ) : (
        <p key={a.id} className="muted">{a.assessment_type}: no results recorded yet.</p>
      ))}
    </div>
  );
}
