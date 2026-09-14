"use client";

import { useEffect, useState } from "react";

type Batch = {
  id: string;
  name: string;
  schedule: string;
  timezone: string;
  capacity: number;
  enrolled_count: number;
  start_date: string;
  end_date: string;
  status: string;
  mode: string;
};
type Student = { id: string; name: string; email: string; batch_id: string };
type Enrollment = { id: string; student_id: string; student: string; batch_id: string; enrollment_code: string; progress_percent: number };
type TrainerContext = { batches: Batch[]; students: Student[]; enrollments: Enrollment[] };

// TRN-002: "Open a batch: student roster (capped at 20 per DEC-WF-002) and
// schedule/status." Each assigned batch renders as its own card with its own roster --
// strictly scoped to that batch's own active enrolments, never mixed with another batch's.
export default function BatchRosterPanel() {
  const [context, setContext] = useState<TrainerContext | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/v1/workflows/it/trainer/context")
      .then((res) => (res.ok ? res.json() : { batches: [], students: [], enrollments: [] }))
      .then((data) => !cancelled && setContext(data))
      .catch(() => !cancelled && setContext({ batches: [], students: [], enrollments: [] }));
    return () => {
      cancelled = true;
    };
  }, []);

  if (!context) {
    return (
      <div className="action-card">
        <h3>Batch roster and schedule</h3>
        <p className="muted">Loading your assigned batches…</p>
      </div>
    );
  }

  if (context.batches.length === 0) {
    return (
      <div className="action-card">
        <h3>Batch roster and schedule</h3>
        <p className="muted">No batches are currently assigned to you.</p>
      </div>
    );
  }

  return (
    <div className="action-card">
      <h3>Batch roster and schedule</h3>
      <div className="grid two" style={{ marginTop: 16 }}>
        {context.batches.map((batch) => {
          const roster = context.enrollments.filter((e) => e.batch_id === batch.id);
          return (
            <div className="card" key={batch.id}>
              <span className="badge">{batch.status}</span>
              <h4 style={{ marginTop: 10 }}>{batch.name}</h4>
              <p className="muted" style={{ fontSize: 13 }}>
                {batch.schedule} · {batch.timezone} · {batch.mode}
              </p>
              <p className="muted" style={{ fontSize: 13 }}>
                {batch.start_date} – {batch.end_date}
              </p>
              <p style={{ fontSize: 13 }}>
                <strong>{batch.enrolled_count}</strong> of {batch.capacity} enrolled
              </p>
              {roster.length ? (
                <table className="table" style={{ marginTop: 8 }}>
                  <thead>
                    <tr>
                      <th scope="col">Student</th>
                      <th scope="col">Enrolment ref</th>
                      <th scope="col">Progress</th>
                    </tr>
                  </thead>
                  <tbody>
                    {roster.map((entry) => (
                      <tr key={entry.id}>
                        <th scope="row">{entry.student}</th>
                        <td>{entry.enrollment_code}</td>
                        <td>{entry.progress_percent}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p className="muted" style={{ fontSize: 13, marginTop: 8 }}>No students enrolled in this batch yet.</p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
