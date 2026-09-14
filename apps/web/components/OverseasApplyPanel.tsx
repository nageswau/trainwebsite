"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { University } from "@/lib/types";

type Course = { id: string; title: string; level: string; category: string; duration: string; tuition_fee: string; intake: string };
type ApplicationRow = { id: string; university: string; reference: string | null; intake: string; status: string; next_action: string | null };
type StatusHistoryEntry = { from_status: string | null; to_status: string; next_action: string | null; changed_at: string };

function detailMessage(status: number, detail: unknown) {
  if (status === 409) return "You already have an application for this university/course.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to submit the application.";
}

// OVS-002: submitting interest previously meant typing a raw university/course UUID
// into a generic form (same class of gap already fixed for ADM-001/002/003/004/006/007).
// This lists real universities (public catalogue, OVS-001) and their real courses instead.
export default function OverseasApplyPanel() {
  const router = useRouter();
  const [universities, setUniversities] = useState<University[] | null>(null);
  const [applications, setApplications] = useState<ApplicationRow[] | null>(null);
  const [universityId, setUniversityId] = useState("");
  const [courses, setCourses] = useState<Course[] | null>(null);
  const [courseId, setCourseId] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const [openHistoryId, setOpenHistoryId] = useState<string | null>(null);
  const [histories, setHistories] = useState<Record<string, StatusHistoryEntry[]>>({});

  useEffect(() => {
    let cancelled = false;
    fetch("/api/v1/public/universities")
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => !cancelled && setUniversities(data))
      .catch(() => !cancelled && setUniversities([]));
    fetch("/api/v1/portal/overseas/student/applications")
      .then((res) => (res.ok ? res.json() : { rows: [] }))
      .then((data) => !cancelled && setApplications(data.rows || []))
      .catch(() => !cancelled && setApplications([]));
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    setCourseId("");
    if (!universityId) {
      setCourses(null);
      return;
    }
    const university = universities?.find((u) => u.id === universityId);
    if (!university) return;
    let cancelled = false;
    fetch(`/api/v1/public/universities/${university.slug}`)
      .then((res) => (res.ok ? res.json() : { courses: [] }))
      .then((data) => !cancelled && setCourses(data.courses || []))
      .catch(() => !cancelled && setCourses([]));
    return () => {
      cancelled = true;
    };
  }, [universityId, universities]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    const form = new FormData(event.currentTarget);
    const response = await fetch("/api/v1/workflows/overseas/applications", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        university_id: universityId,
        course_id: courseId || null,
        intake: String(form.get("intake") || "Next intake"),
      }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setMessage({ text: detailMessage(response.status, data.detail), failed: true });
      return;
    }
    setMessage({ text: "Application submitted -- track its status below.", failed: false });
    setUniversityId("");
    setCourses(null);
    router.refresh();
    fetch("/api/v1/portal/overseas/student/applications")
      .then((res) => (res.ok ? res.json() : { rows: [] }))
      .then((data) => setApplications(data.rows || []));
  }

  function toggleHistory(applicationId: string) {
    if (openHistoryId === applicationId) {
      setOpenHistoryId(null);
      return;
    }
    setOpenHistoryId(applicationId);
    if (!histories[applicationId]) {
      fetch(`/api/v1/workflows/overseas/applications/${applicationId}/status`)
        .then((res) => (res.ok ? res.json() : { history: [] }))
        .then((data) => setHistories((current) => ({ ...current, [applicationId]: data.history || [] })));
    }
  }

  if (universities === null || applications === null) {
    return (
      <div className="action-card">
        <h3>Apply to a University</h3>
        <p className="muted">Loading universities…</p>
      </div>
    );
  }

  return (
    <div className="action-card">
      <h3>Apply to a University</h3>
      <form className="form" onSubmit={submit}>
        <div className="field">
          <label htmlFor="apply-university">University</label>
          <select id="apply-university" value={universityId} onChange={(event) => setUniversityId(event.target.value)} required>
            <option value="">Select a university…</option>
            {universities.map((u) => (
              <option key={u.id} value={u.id}>{u.name} -- {u.city}</option>
            ))}
          </select>
        </div>
        {universityId && (
          <div className="field">
            <label htmlFor="apply-course">Course (optional)</label>
            <select id="apply-course" value={courseId} onChange={(event) => setCourseId(event.target.value)} disabled={courses === null}>
              <option value="">Undecided / any course</option>
              {(courses || []).map((c) => (
                <option key={c.id} value={c.id}>{c.title} ({c.level})</option>
              ))}
            </select>
          </div>
        )}
        <div className="field">
          <label htmlFor="apply-intake">Intake</label>
          <input id="apply-intake" name="intake" defaultValue="Next intake" required />
        </div>
        <button className="btn small" disabled={busy || !universityId}>
          {busy ? "Submitting…" : "Submit interest"}
        </button>
      </form>
      {message && (
        <div className={message.failed ? "form-error" : "form-message"} role="status" aria-live="polite" style={{ marginTop: 8 }}>
          {message.text}
        </div>
      )}
      <h4 style={{ marginTop: 24 }}>Your applications</h4>
      {applications.length === 0 ? (
        <p className="muted">You have not applied to any university yet.</p>
      ) : (
        <div className="grid two">
          {applications.map((a) => (
            <div className="card" key={a.id}>
              <span className="badge">{a.status}</span>
              <h4 style={{ marginTop: 10 }}>{a.university}</h4>
              <p className="muted" style={{ fontSize: 13 }}>{a.intake}</p>
              {a.next_action && <p className="muted" style={{ fontSize: 13 }}>{a.next_action}</p>}
              <button className="btn small" onClick={() => toggleHistory(a.id)}>
                {openHistoryId === a.id ? "Hide status history" : "View status history"}
              </button>
              {openHistoryId === a.id && (
                <ul className="list-clean" style={{ marginTop: 8 }}>
                  {histories[a.id] === undefined ? (
                    <li className="muted">Loading…</li>
                  ) : histories[a.id].length === 0 ? (
                    <li className="muted">No status changes recorded yet.</li>
                  ) : (
                    histories[a.id].map((entry, index) => (
                      <li key={index}>
                        <strong>{entry.to_status.replaceAll("_", " ")}</strong> — <span className="muted">{new Date(entry.changed_at).toLocaleDateString()}</span>
                      </li>
                    ))
                  )}
                </ul>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
