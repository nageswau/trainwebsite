import Link from "next/link";
import { Fragment } from "react";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import HrDocumentDownload from "@/components/HrDocumentDownload";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { classesParts, HR_STUDENTS_API, HR_STUDENTS_PATH, percent, statusLabel, type HrStudentDetail } from "@/lib/hrStudents";
import { PORTAL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

const WITHHELD = "Not available to your role.";

// nehn-017 (DEC-SCOPE-310): one student's training for HR -- progress, completion, attendance and the document types HR may open. Each
// block the API withholds (a revoked grant) says so instead of disappearing silently. Nothing financial is ever sent.
export default async function HrStudentPage({ id }: { id: string }) {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/it/login");
  }
  if (user.role !== "hr_team") return accessDenied(user, "HR role required");
  let detail: HrStudentDetail | null = null;
  let error = "";
  try {
    detail = await serverApi<HrStudentDetail>(`${HR_STUDENTS_API}/${encodeURIComponent(id)}`);
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return accessUnavailable(e, "/it/login");
    error = e instanceof ApiError && (e.status === 404 || e.status === 422) ? "This student isn't in your list." : "This student is unavailable right now. Please try again.";
  }
  return (
    <PortalShell nav={PORTAL_NAV["it/hr"]} roleLabel="HR Team" userName={user.full_name}>
      <div className="portal-content">
        <p><Link href={HR_STUDENTS_PATH}>← All students</Link></p>
        {!detail ? (
          <div className="action-card"><p className="form-error" role="alert">{error}</p></div>
        ) : (
          <>
            <div className="portal-title">
              <div>
                <div className="eyebrow">Student{detail.student.student_code ? ` · ${detail.student.student_code}` : ""}</div>
                <h2>{detail.student.full_name}</h2>
                <p className="muted">Read only. Progress, completion and attendance are the training records; a course is completed at 100% progress.</p>
              </div>
            </div>
            <div className="action-card">
              <h3>Courses</h3>
              {!detail.can.attendance && <p className="muted">Attendance: {WITHHELD}</p>}
              {detail.seats.length === 0 ? <p className="muted">No course enrolments yet.</p> : (
                <div className="table-wrap">
                  <table className="table stack stack-wide compact hr-student-table" aria-label="Courses">
                    <thead>
                      <tr>
                        <th scope="col">Course</th><th scope="col">Batch</th><th scope="col">Trainer</th><th scope="col">Status</th>
                        <th scope="col">Progress</th><th scope="col">Completed</th><th scope="col">Certificate</th>
                        {detail.can.attendance && <th scope="col">Attendance</th>}
                      </tr>
                    </thead>
                    <tbody>
                      {detail.seats.map((seat, i) => (
                        <tr key={`${seat.batch}-${i}`}>
                          <th scope="row" data-label="Course">{seat.course}</th>
                          <td data-label="Batch">{seat.batch}</td>
                          <td data-label="Trainer">{seat.trainer ?? "—"}</td>
                          <td data-label="Status">{statusLabel(seat.status)}</td>
                          <td data-label="Progress">{percent(seat.progress)}</td>
                          <td data-label="Completed">{seat.completed ? "Yes" : "No"}</td>
                          <td data-label="Certificate">{statusLabel(seat.certificate)}</td>
                          {seat.attendance && (
                              <td data-label="Attendance">
                                <div>
                                  <strong>{percent(seat.attendance.attendance_pct)}</strong>
                                  <div className="muted" style={{ fontSize: 12 }}>
                                    {classesParts(seat.attendance).map((part, n) => <Fragment key={part}>{n > 0 && " · "}<span className="nowrap">{part}</span></Fragment>)}
                                  </div>
                                </div>
                              </td>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
            <div className="action-card">
              <h3>Documents</h3>
              {!detail.documents ? <p className="muted">{WITHHELD}</p> : detail.documents.length === 0 ? (
                <p className="muted">No resume, CV, portfolio or certificate uploaded.</p>
              ) : (
                <ul style={{ display: "grid", gap: 8, paddingLeft: 0, listStyle: "none" }}>
                  {detail.documents.map((doc) => {
                    const name = doc.original_filename || doc.document_type;
                    return (
                      <li key={doc.id} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", overflowWrap: "anywhere" }}>
                        <span><strong>{doc.document_type.trim()}</strong> · {name}</span>
                        {detail.can.download && <HrDocumentDownload studentId={detail.student.id} documentId={doc.id} name={name} />}
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </>
        )}
      </div>
    </PortalShell>
  );
}
