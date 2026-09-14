"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

type ApplicationRow = { id: string; student: string; university: string; reference: string | null; status: string; next_action: string | null };

// DATA_MODEL.md #6.2's contract-fixed enum -- kept in this order so "later stages" can
// be offered as the only valid `to_status` choices for a given row (OVS-003-AC02:
// exception-path values like rejected/waitlisted/deferred are a deliberate open item,
// never offered here).
const STAGES = ["enquiry", "eligibility_evaluation", "university_selection", "offer", "visa_documentation", "status_tracking", "enrolled"];
const label = (stage: string) => stage.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to advance this application.";
}

// OVS-003: a Counselor previously had to type a raw application UUID and pick a status
// from a list that included values ("rejected", "submitted", ...) the backend never
// actually supported -- same class of gap already fixed for
// ADM-001/002/003/004/006/007. This lists only the Counselor's own assigned
// applications (server-enforced, not just hidden here) and offers only the stages
// still ahead of each one.
export default function CounselorEvaluationPanel() {
  const router = useRouter();
  const [rows, setRows] = useState<ApplicationRow[] | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<{ id: string; text: string; failed: boolean } | null>(null);

  function load() {
    fetch("/api/v1/portal/overseas/counselor/applications")
      .then((res) => (res.ok ? res.json() : { rows: [] }))
      .then((data) => setRows(data.rows || []))
      .catch(() => setRows([]));
  }

  useEffect(load, []);

  async function submit(event: FormEvent<HTMLFormElement>, applicationId: string) {
    event.preventDefault();
    setBusyId(applicationId);
    setMessage(null);
    const form = new FormData(event.currentTarget);
    const response = await fetch(`/api/v1/workflows/overseas/applications/${applicationId}/advance`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ to_status: String(form.get("to_status")), next_action: String(form.get("next_action") || "") || null }),
    });
    const data = await response.json().catch(() => ({}));
    setBusyId(null);
    if (!response.ok) {
      setMessage({ id: applicationId, text: detailMessage(data.detail), failed: true });
      return;
    }
    setMessage({ id: applicationId, text: "Application advanced -- the student has been notified.", failed: false });
    setOpenId(null);
    router.refresh();
    load();
  }

  if (rows === null) {
    return (
      <div className="action-card">
        <h3>Evaluate Applications</h3>
        <p className="muted">Loading your assigned applications…</p>
      </div>
    );
  }

  if (rows.length === 0) {
    return (
      <div className="action-card">
        <h3>Evaluate Applications</h3>
        <p className="muted">No applications are assigned to you yet.</p>
      </div>
    );
  }

  return (
    <div className="action-card">
      <h3>Evaluate Applications</h3>
      <div className="grid two" style={{ marginTop: 16 }}>
        {rows.map((row) => {
          const currentIndex = STAGES.indexOf(row.status);
          const nextStages = STAGES.slice(currentIndex + 1);
          return (
            <div className="card" key={row.id}>
              <span className="badge">{label(row.status)}</span>
              <h4 style={{ marginTop: 10 }}>{row.student}</h4>
              <p className="muted" style={{ fontSize: 13 }}>{row.university}</p>
              {row.next_action && <p className="muted" style={{ fontSize: 13 }}>{row.next_action}</p>}
              {nextStages.length === 0 ? (
                <p className="muted" style={{ fontSize: 13 }}>No further stage to advance to.</p>
              ) : openId === row.id ? (
                <form className="form" onSubmit={(event) => submit(event, row.id)}>
                  <div className="field">
                    <label htmlFor={`to-status-${row.id}`}>Advance to</label>
                    <select id={`to-status-${row.id}`} name="to_status" required>
                      {nextStages.map((stage) => (
                        <option key={stage} value={stage}>{label(stage)}</option>
                      ))}
                    </select>
                  </div>
                  <div className="field">
                    <label htmlFor={`next-action-${row.id}`}>Next action for the student</label>
                    <textarea id={`next-action-${row.id}`} name="next_action" />
                  </div>
                  <button className="btn small" disabled={busyId === row.id}>
                    {busyId === row.id ? "Advancing…" : "Advance"}
                  </button>
                </form>
              ) : (
                <button className="btn small" onClick={() => setOpenId(row.id)}>Advance stage</button>
              )}
              {message?.id === row.id && (
                <div className={message.failed ? "form-error" : "form-message"} role="status" aria-live="polite" style={{ marginTop: 8 }}>
                  {message.text}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
