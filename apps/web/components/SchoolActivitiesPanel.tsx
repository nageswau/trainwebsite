"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { isFeedbackEligible } from "@/lib/activityFeedback";

type Activity = { id: string; title: string; scheduled_at: string; activity_type?: string | null };
type Student = { id: string; full_name: string };

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Something went wrong.";
}

// SCH-001: schedule an activity, mark who attended -- for the Coordinator's own
// institution only.
export default function SchoolActivitiesPanel({ activities, students }: { activities: Activity[]; students: Student[] }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const [markingId, setMarkingId] = useState<string | null>(null);
  const [present, setPresent] = useState<Record<string, boolean>>({});

  async function schedule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    setBusy(true);
    setMessage(null);
    const form = new FormData(formElement);
    const response = await fetch("/api/v1/school/activities", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: form.get("title"), scheduled_at: new Date(String(form.get("scheduled_at"))).toISOString(), activity_type: form.get("activity_type") || undefined }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setMessage({ text: detailMessage(data.detail), failed: true });
      return;
    }
    setMessage({ text: `${data.title} scheduled.`, failed: false });
    formElement.reset();
    router.refresh();
  }

  function startMarking(activityId: string) {
    setMarkingId(activityId);
    setPresent(Object.fromEntries(students.map((s) => [s.id, true])));
  }

  async function submitAttendance(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!markingId) return;
    setBusy(true);
    setMessage(null);
    const records = students.map((s) => ({ student_id: s.id, present: !!present[s.id] }));
    const response = await fetch(`/api/v1/school/activities/${markingId}/attendance`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ records }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setMessage({ text: detailMessage(data.detail), failed: true });
      return;
    }
    setMessage({ text: `Attendance recorded for ${data.marked} student(s).`, failed: false });
    setMarkingId(null);
    router.refresh();
  }

  return (
    <div className="portal-content">
      <div className="card">
        <h2>Activities</h2>
        {activities.length === 0 ? (
          <p className="muted">Nothing scheduled yet.</p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th>Title</th><th>When</th><th>Actions</th></tr>
              </thead>
              <tbody>
                {activities.map((a) => (
                  <tr key={a.id}>
                    <td>{a.title}</td>
                    <td>{new Date(a.scheduled_at).toLocaleString()}</td>
                    <td>
                      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                        <button className="btn ghost small" onClick={() => startMarking(a.id)}>Mark attendance</button>
                        {/* ENH-018: completed Edusphere (typed) activities link to the Feedback page. */}
                        {isFeedbackEligible(a) && <Link className="btn secondary small" href="/school/coordinator/feedback" aria-label={`Give feedback for ${a.title}`}>Give feedback</Link>}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {markingId && (
        <div className="action-card">
          <h3>Mark attendance</h3>
          {students.length === 0 ? (
            <p className="muted">No students on your roster yet.</p>
          ) : (
            <form className="form" onSubmit={submitAttendance}>
              {students.map((s) => (
                <label key={s.id} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <input
                    type="checkbox"
                    checked={!!present[s.id]}
                    onChange={(e) => setPresent((p) => ({ ...p, [s.id]: e.target.checked }))}
                  />
                  {s.full_name}
                </label>
              ))}
              <div className="field" style={{ flexDirection: "row", gap: 12 }}>
                <button className="btn" disabled={busy}>{busy ? "Saving…" : "Save attendance"}</button>
                <button type="button" className="btn secondary" onClick={() => setMarkingId(null)}>Cancel</button>
              </div>
            </form>
          )}
        </div>
      )}

      <div className="action-card">
        <h3>Schedule an activity</h3>
        <form className="form" onSubmit={schedule}>
          <div className="field">
            <label htmlFor="activity-title">Title</label>
            <input id="activity-title" name="title" required />
          </div>
          <div className="field">
            <label htmlFor="activity-when">Date &amp; time</label>
            <input id="activity-when" name="scheduled_at" type="datetime-local" required />
          </div>
          <div className="field">
            <label htmlFor="activity-type">Entitlement category (optional)</label>
            <select id="activity-type" name="activity_type" defaultValue="">
              <option value="">None</option>
              <option value="career_seminar">Career seminar</option>
              <option value="career_awareness_session">Student career awareness session</option>
              <option value="parent_orientation">Parent orientation</option>
              <option value="campus_visit">Monthly campus visit</option>
            </select>
          </div>
          <button className="btn" disabled={busy}>{busy ? "Scheduling…" : "Schedule activity"}</button>
        </form>
      </div>

      {message && (
        <div className={message.failed ? "form-error" : "form-message"} role="status" aria-live="polite">
          {message.text}
        </div>
      )}
    </div>
  );
}
