"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import FormMessage, { type FormMessageState } from "@/components/FormMessage";
import { sendJson } from "@/lib/apiErrors";
import { formatSchoolDateTime } from "@/lib/formatDate";

type Activity = { id: string; title: string; scheduled_at: string };
type Student = { id: string; full_name: string };

// SCH-001: schedule an activity, mark who attended -- for the Coordinator's own
// institution only.
export default function SchoolActivitiesPanel({ activities, students }: { activities: Activity[]; students: Student[] }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  // ENH-022: which form the message belongs to, so it renders beside that form.
  const [message, setMessage] = useState<(FormMessageState & { form: "schedule" | "attendance" }) | null>(null);
  const [markingId, setMarkingId] = useState<string | null>(null);
  const [present, setPresent] = useState<Record<string, boolean>>({});

  async function schedule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    setBusy(true);
    setMessage(null);
    const form = new FormData(formElement);
    const result = await sendJson("/api/v1/school/activities", "POST", {
      title: form.get("title"),
      scheduled_at: new Date(String(form.get("scheduled_at"))).toISOString(),
      activity_type: form.get("activity_type") || undefined,
    });
    setBusy(false);
    if (!result.ok) {
      setMessage({ text: result.message, failed: true, form: "schedule" });
      return;
    }
    setMessage({ text: `${result.data.title} scheduled.`, failed: false, form: "schedule" });
    formElement.reset();
    router.refresh();
  }

  // QA-022-01: an attendance message belongs to the card that produced it -- opening or cancelling the card starts clean.
  function clearAttendanceMessage() {
    setMessage((current) => (current?.form === "attendance" ? null : current));
  }

  function startMarking(activityId: string) {
    clearAttendanceMessage();
    setMarkingId(activityId);
    setPresent(Object.fromEntries(students.map((s) => [s.id, true])));
  }

  function stopMarking() {
    clearAttendanceMessage();
    setMarkingId(null);
  }

  async function submitAttendance(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!markingId) return;
    setBusy(true);
    setMessage(null);
    const records = students.map((s) => ({ student_id: s.id, present: !!present[s.id] }));
    const result = await sendJson(`/api/v1/school/activities/${markingId}/attendance`, "POST", { records });
    setBusy(false);
    if (!result.ok) {
      setMessage({ text: result.message, failed: true, form: "attendance" });
      return;
    }
    // The attendance card closes on success, so this confirmation shows under the schedule form instead.
    setMessage({ text: `Attendance recorded for ${result.data.marked} student(s).`, failed: false, form: "schedule" });
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
                    <td>{formatSchoolDateTime(a.scheduled_at, true)}</td>
                    <td><button className="btn ghost small" onClick={() => startMarking(a.id)}>Mark attendance</button></td>
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
                <button type="button" className="btn secondary" onClick={stopMarking}>Cancel</button>
              </div>
            </form>
          )}
          {message?.form === "attendance" && <FormMessage message={message} />}
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
        {message?.form === "schedule" && <FormMessage message={message} />}
      </div>
    </div>
  );
}
