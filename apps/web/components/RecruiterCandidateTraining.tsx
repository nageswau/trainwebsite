"use client";
import { useEffect, useId, useState } from "react";

import { statusLabel } from "@/lib/candidateJourney";
import { type CandidateTraining, candidateTrainingUrl, isCandidateTraining } from "@/lib/candidateTraining";
import { formatCalendarDate } from "@/lib/formatDate";

const pct = (value: number | null) => (value === null ? "—" : `${value}%`);

/** nehn-016 (DEC-SCOPE-309): the student's training progress for the recruiter -- course, batch, dates, status, progress, attendance (as
 *  certificate eligibility counts it; "—" when nothing is marked), assignments, assessments, the certificate and placement readiness.
 *  Read only; on a phone the table stacks into labelled blocks. */
export default function RecruiterCandidateTraining({ candidateId }: { candidateId: string }) {
  const [training, setTraining] = useState<CandidateTraining | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const headingId = `${useId()}-training`;

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    fetch(candidateTrainingUrl(candidateId), { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((body) => (isCandidateTraining(body) ? setTraining(body) : setFailed(true)))
      .catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [candidateId, version]);

  const readiness = training?.readiness;
  return (
    <section className="action-card wide" aria-labelledby={headingId}>
      <h3 id={headingId} style={{ margin: 0 }}>Training progress</h3>
      {failed ? (
        <div>
          <p className="form-error" role="alert" style={{ fontSize: 13 }}>Unable to load training progress.</p>
          <button type="button" className="btn secondary small" onClick={() => setVersion((n) => n + 1)}>Retry</button>
        </div>
      ) : training === null ? (
        <p className="muted" role="status" style={{ fontSize: 13 }}>Loading training progress…</p>
      ) : !training.student ? (
        <p className="muted" style={{ fontSize: 13 }}>Not an EduSphere IT student — no training to show.</p>
      ) : (
        <>
          {readiness && (
            <p style={{ margin: 0, fontSize: 14 }}>
              <span className="muted">Readiness:</span> {statusLabel(readiness.readiness_status)} · resume {statusLabel(readiness.resume_status)} ·
              {" "}mock interview {statusLabel(readiness.mock_interview_status)} · aptitude {statusLabel(readiness.aptitude_status)}
              {readiness.available ? " · available" : ""}
            </p>
          )}
          {training.seats.length === 0 ? (
            <p className="muted" style={{ fontSize: 13 }}>No course enrolments yet.</p>
          ) : (
            <div className="table-scroll candidate-training" tabIndex={0} role="region" aria-label="Training progress by course">
              <table className="table compact stack">
                <caption className="visually-hidden">Training progress</caption>
                <thead>
                  <tr>
                    {/* QA16-01: the batch sits under the course and the headers are short, so every column fits the card on a desktop; the
                        cells carry "graded" / "passed". */}
                    {["Course", "Trainer", "Ends", "Status", "Progress", "Attendance", "Assignments", "Assessments", "Certificate"].map(
                      (label) => <th key={label} scope="col">{label}</th>,
                    )}
                  </tr>
                </thead>
                <tbody>
                  {training.seats.map((s) => (
                    <tr key={`${s.course}-${s.batch}`}>
                      <th scope="row">{s.course}<br /><span className="muted" style={{ fontWeight: 400 }}>{s.batch}</span></th>
                      <td data-label="Trainer">{s.trainer ?? "—"}</td>
                      <td data-label="Batch ends" className="nowrap">{formatCalendarDate(s.ends)}</td>
                      <td data-label="Status">{statusLabel(s.status)}</td>
                      <td data-label="Progress" className="num">{pct(s.progress)}</td>
                      <td data-label="Attendance" className="num">{pct(s.attendance_pct)}</td>
                      <td data-label="Assignments" className="nowrap">{s.assignments_graded} / {s.assignments_total} graded</td>
                      <td data-label="Assessments" className="nowrap">{s.assessments_passed} / {s.assessments_total} passed</td>
                      <td data-label="Certificate">{statusLabel(s.certificate)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}
