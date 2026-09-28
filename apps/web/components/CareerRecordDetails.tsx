import { CAREER_LIST_FIELDS, type CareerRecord, statusLabel } from "@/lib/careerRecords";
import { formatCalendarDate, formatSchoolDateTime } from "@/lib/formatDate";

const yesNo = (value: boolean | null | undefined) => (value === true ? "Yes" : value === false ? "No" : null);

// ENH-026: the structured part of one counselling/guidance record, read-only. Empty fields are omitted (spec §11.2 F6); status is
// always text in the shared .status chip, never colour alone (F10).
export default function CareerRecordDetails({ record }: { record: CareerRecord }) {
  const rows: [string, string][] = [];
  if (record.scheduled_for) rows.push(["Scheduled for", formatSchoolDateTime(record.scheduled_for)]);
  if (record.completed_on) rows.push(["Completed on", formatCalendarDate(record.completed_on)]);
  if (record.next_follow_up_date) rows.push(["Next follow-up", formatCalendarDate(record.next_follow_up_date)]);
  for (const field of CAREER_LIST_FIELDS) {
    const items = record[field.key];
    if (items?.length) rows.push([field.label, items.join(", ")]);
  }
  const global = yesNo(record.global_education_interest);
  if (global) rows.push(["Interested in global education", global]);
  const parent = yesNo(record.parent_participated);
  if (parent) rows.push(["Parent participated", record.parent_participation_note ? `${parent} — ${record.parent_participation_note}` : parent]);
  if (record.counselor_name) rows.push(["Counsellor", record.counselor_name]);

  return (
    <div className="record-details-block">
      <span className={`status${record.status === "completed" ? "" : " pending"}`}>{statusLabel(record.status)}</span>
      {rows.length > 0 && (
        <dl className="record-details">
          {rows.map(([term, value]) => (
            <div key={term} className="record-details-row"><dt>{term}</dt><dd>{value}</dd></div>
          ))}
        </dl>
      )}
    </div>
  );
}
