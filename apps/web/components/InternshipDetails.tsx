"use client";

import InternshipCertificate from "@/components/InternshipCertificate";
import { COMPLETION_LABEL } from "@/lib/internship";
import type { PortfolioEntry } from "@/lib/portfolio";

// ENH-021: an internship entry's tracking fields, read-only; empty fields omitted, status always in words (spec §11.2 F6/F10).
export default function InternshipDetails({ entry, studentId, canEdit }: { entry: PortfolioEntry; studentId: string; canEdit: boolean }) {
  const mentor = [entry.mentor_name, entry.mentor_designation].filter(Boolean).join(", ");
  const rows: [string, string][] = [];
  if (mentor) rows.push(["Mentor", mentor]);
  if (entry.attendance_percent != null) rows.push(["Attendance", `${entry.attendance_percent}%`]);
  if (entry.skills_acquired?.length) rows.push(["Skills acquired", entry.skills_acquired.join(", ")]);
  if (entry.feedback) rows.push(["Feedback", entry.feedback]);
  return (
    <div className="internship-details">
      <span className={`status${entry.completion_status === "completed" ? "" : " pending"}`}>{entry.completion_status ? COMPLETION_LABEL[entry.completion_status] ?? entry.completion_status : "No status"}</span>
      {rows.length > 0 && (
        <dl className="record-details">
          {rows.map(([term, value]) => <div key={term} className="record-details-row"><dt>{term}</dt><dd>{value}</dd></div>)}
        </dl>
      )}
      <InternshipCertificate studentId={studentId} entryId={entry.id} hasCertificate={Boolean(entry.has_certificate)} contentType={entry.certificate_content_type ?? null} canEdit={canEdit} completed={entry.completion_status === "completed"} />
    </div>
  );
}
