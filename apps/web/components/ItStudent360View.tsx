import Link from "next/link";
import type { ReactNode } from "react";

import { FeeAccountCard } from "@/components/FeeAccountSummary";
import LeadTimeline from "@/components/LeadTimeline";
import LocalTime from "@/components/LocalTime";
import { formatCalendarDate } from "@/lib/formatDate";
import { riskReasonLabels } from "@/lib/itAtRisk";
import { authorRole } from "@/lib/itStudentNotes";
import { leadTimelineUrl, percentText, type Portal360, type Student360 } from "@/lib/itStudent360";
import { resumeFileUrl, studentResumesUrl, uploaderLabel } from "@/lib/studentResumes";

const money = (value: number) => `INR ${value.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const fileSize = (bytes: number) => (bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB`);
const humanize = (value: string) => value.charAt(0).toUpperCase() + value.slice(1).replaceAll("_", " ");
const dateRange = (start: string | null, end: string | null) => (start || end ? `${formatCalendarDate(start)} – ${formatCalendarDate(end)}` : "—");

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section className="action-card" aria-labelledby={`s360-${id}`}>
      <h3 id={`s360-${id}`}>{title}</h3>
      {children}
    </section>
  );
}

function Facts({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="fee-account-figures">
      {rows.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value || "—"}</dd>
        </div>
      ))}
    </dl>
  );
}

/** itc-029 (DEC-SCOPE-360): the 360's sections in the spec's order. Each is rendered only when the API sent it (the per-role allow-list
 *  lives on the server); every edit stays on its own page, linked from here. */
export default function ItStudent360View({ portal, data }: { portal: Portal360; data: Student360 }) {
  const { student, contact, profile, lead, enrollments, fee, risk, feedback, resumes, hr_review: review, notes, notifications } = data;
  const resumeList = studentResumesUrl(portal, student.id);
  const notesHref = `/it/${portal}/students/${encodeURIComponent(student.id)}/notes`;
  const attendance = enrollments.some((e) => "attendance_percent" in e); // HR without `attendance.view` gets no figures
  return (
    <div className="grid it-student-360" style={{ gap: 16 }}>
      <Section id="contact" title="Contact">
        <Facts
          rows={[
            ["Email", contact.email],
            ["Phone", contact.phone],
            ["Counselor", contact.counselor?.full_name ?? "Not assigned"],
            ...(profile
              ? ([
                  ["City", profile.city],
                  ["Qualification", profile.qualification],
                  ["Emergency contact", [profile.emergency_contact_name, profile.emergency_contact_relation && `(${profile.emergency_contact_relation})`, profile.emergency_contact_phone].filter(Boolean).join(" ")],
                  ["Phone calls", profile.calls_allowed ? "Allowed" : "Opted out"],
                ] as [string, ReactNode][])
              : []),
          ]}
        />
      </Section>

      {lead !== undefined && (
        <Section id="lead" title="Lead history">
          {lead === null ? (
            <p className="muted">This student did not come from an IT lead.</p>
          ) : (
            <>
              <p>
                {lead.href ? <Link href={lead.href}>{lead.lead_code}</Link> : lead.lead_code} · {lead.stage_label}
                {lead.owner ? ` · owner ${lead.owner}` : ""} · created <LocalTime value={lead.created_at} />
                {lead.converted_at && <> · converted <LocalTime value={lead.converted_at} /></>}
              </p>
              <LeadTimeline url={leadTimelineUrl(student.id)} version={0} label="Lead activity before enrolment" />
            </>
          )}
        </Section>
      )}

      <Section id="courses" title="Courses and progress">
        {enrollments.length === 0 ? (
          <p className="muted">No enrolments yet.</p>
        ) : (
          <div className="table-wrap">
            <table className="table stack compact" aria-label="Courses and progress">
              <thead>
                <tr>
                  <th scope="col">Course</th><th scope="col">Trainer</th><th scope="col">Dates</th><th scope="col">Mode</th><th scope="col">Status</th>
                  <th scope="col">Progress</th>{attendance && <th scope="col">Attendance</th>}
                </tr>
              </thead>
              <tbody>
                {enrollments.map((e) => (
                  <tr key={e.id}>
                    <td data-label="Course"><div>{e.program}<div className="muted" style={{ fontSize: 13 }}>{e.batch} · {e.enrollment_code}</div></div></td>
                    <td data-label="Trainer">{e.trainer ?? "—"}</td>
                    <td data-label="Dates">{dateRange(e.start_date, e.end_date)}</td>
                    <td data-label="Mode">{e.delivery_mode ?? "—"}</td>
                    <td data-label="Status">{humanize(e.status)}</td>
                    <td data-label="Progress">{percentText(e.progress_percent)}</td>
                    {attendance && <td data-label="Attendance">{e.attendance_marked ? percentText(e.attendance_percent) : "No classes marked"}</td>}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {enrollments.length > 0 && !attendance && <p className="muted">Attendance: not available to your role.</p>}
      </Section>

      {risk !== undefined && (
        <Section id="risk" title="Risk">
          {risk.length === 0 ? (
            <p className="muted">Not flagged at risk.</p>
          ) : (
            <ul>
              {risk.map((flag) => (
                <li key={flag.enrollment_id}>
                  <span className="badge">At risk</span> {flag.batch}: {riskReasonLabels(flag).join("; ")} · since <LocalTime value={flag.raised_at} />
                </li>
              ))}
            </ul>
          )}
        </Section>
      )}

      {fee !== undefined && (
        <Section id="fee" title="Fees">
          {fee.accounts.length === 0 ? (
            <p className="muted">No fee account yet: the student has no enrolment.</p>
          ) : (
            <>
              <p><strong>Total balance: {fee.balance === null ? "nothing billed" : money(fee.balance)}</strong></p>
              <div className="grid two">{fee.accounts.map((account) => <FeeAccountCard key={account.enrollment_id} account={account} />)}</div>
            </>
          )}
        </Section>
      )}

      <Section id="feedback" title="Recent trainer feedback">
        {feedback.length === 0 ? (
          <p className="muted">No graded feedback yet.</p>
        ) : (
          <ul>
            {feedback.map((f) => (
              <li key={`${f.kind}-${f.title}-${f.at}`}>
                <strong>{f.title}</strong> ({f.kind}{f.score !== null ? `, ${f.score}/${f.max_score}` : ""}){f.by ? ` · ${f.by}` : ""} · <LocalTime value={f.at} />
                <div>{f.feedback}</div>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section id="resumes" title="Resume and HR stage">
        <p>
          HR stage:{" "}
          {review.task ? (
            <>
              <span className="badge">{review.task.stage_label}</span> {review.task.next_action}
              {review.task.owner ? ` · HR owner ${review.task.owner.full_name}` : " · no HR owner yet"}
            </>
          ) : (
            "No HR review yet."
          )}
        </p>
        {resumes.items.length === 0 ? (
          <p className="muted">{portal === "hr" ? "No resume shared with HR yet." : "No resume uploaded yet."}</p>
        ) : (
          <ul>
            {resumes.items.map((v, i) => (
              <li key={v.version}>
                <a href={resumeFileUrl(resumeList, v.version)} aria-label={`Download resume version ${v.version}`}>Version {v.version}</a>
                {i === 0 && " (current)"} · {fileSize(v.size_bytes)}
                {portal !== "hr" && ` · ${v.visibility === "hr" ? "shared with HR" : "private"}`}
                {uploaderLabel(v) && ` · ${uploaderLabel(v)}`} · <LocalTime value={v.created_at} />
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section id="notes" title="Notes">
        {notes.items.length === 0 ? (
          <p className="muted">No notes yet.</p>
        ) : (
          <ul>
            {notes.items.map((note) => (
              <li key={note.id}>
                <span className="badge">{note.visibility === "student" ? "Shared with student" : "Internal"}</span> {note.body}
                <div className="muted" style={{ fontSize: 13 }}>{note.author_name} ({authorRole(note.author_role)}) · <LocalTime value={note.created_at} time /></div>
              </li>
            ))}
          </ul>
        )}
        <p><Link href={notesHref}>{notes.total > notes.items.length ? `All ${notes.total} notes` : "Open notes"}</Link></p>
      </Section>

      {notifications !== undefined && (
        <Section id="notifications" title="Notifications sent">
          {notifications.length === 0 ? (
            <p className="muted">No notifications sent to the student yet.</p>
          ) : (
            <ul>
              {notifications.map((n) => (
                <li key={n.id}>
                  {n.title} · <LocalTime value={n.sent_at} time /> · {n.read ? "read" : "unread"}
                </li>
              ))}
            </ul>
          )}
        </Section>
      )}
    </div>
  );
}
