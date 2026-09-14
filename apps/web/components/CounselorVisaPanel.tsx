"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

type ApplicationRow = { id: string; student: string; university: string };
type ChecklistItem = { item: string; verification_status: string };
type Checklist = { exists: boolean; id?: string; status: string | null; checklist: ChecklistItem[] };
type VisaStatus = { exists: boolean; status: string | null; appointment_date: string | null; tracking_reference: string | null; disclaimer: string };

const STAGES = ["checklist", "documentation", "interview_prep", "tracking", "decision"];
const label = (stage: string) => stage.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
const DEFAULT_DISCLAIMER = "Visa decisions are made by the relevant government or immigration authority. EduSphere does not decide visa outcomes.";

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to complete this action.";
}

// VISA-001: a Counselor previously had to type a raw application UUID (to start a case)
// or a raw visa-case UUID plus a free-typed status (to update one), with no visibility
// into which of their assigned applications already had a case or what its checklist
// items' real verification state was -- same class of gap already fixed for
// ADM-001/002/003/004/006/007. This lists the Counselor's own assigned applications,
// each with its checklist (if started) and a real, forward-only stage control.
export default function CounselorVisaPanel() {
  const router = useRouter();
  const [applications, setApplications] = useState<ApplicationRow[] | null>(null);
  const [checklists, setChecklists] = useState<Record<string, Checklist>>({});
  const [statuses, setStatuses] = useState<Record<string, VisaStatus>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<{ id: string; text: string; failed: boolean } | null>(null);

  function loadChecklist(applicationId: string) {
    fetch(`/api/v1/workflows/overseas/applications/${applicationId}/visa-checklist`)
      .then((res) => (res.ok ? res.json() : null))
      .then((checklist) => checklist && setChecklists((current) => ({ ...current, [applicationId]: checklist })));
    fetch(`/api/v1/workflows/overseas/applications/${applicationId}/visa-status`)
      .then((res) => (res.ok ? res.json() : null))
      .then((status) => status && setStatuses((current) => ({ ...current, [applicationId]: status })));
  }

  function load() {
    fetch("/api/v1/portal/overseas/counselor/applications")
      .then((res) => (res.ok ? res.json() : { rows: [] }))
      .then((data) => {
        const rows = (data.rows || []) as ApplicationRow[];
        setApplications(rows);
        rows.forEach((row) => loadChecklist(row.id));
      })
      .catch(() => setApplications([]));
  }

  useEffect(load, []);

  async function startCase(event: FormEvent<HTMLFormElement>, applicationId: string) {
    event.preventDefault();
    setBusyId(applicationId);
    setMessage(null);
    const form = new FormData(event.currentTarget);
    const checklist = String(form.get("checklist") || "").split(",").map((s) => s.trim()).filter(Boolean);
    const response = await fetch("/api/v1/workflows/overseas/visa", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ application_id: applicationId, checklist }),
    });
    const data = await response.json().catch(() => ({}));
    setBusyId(null);
    if (!response.ok) {
      setMessage({ id: applicationId, text: detailMessage(data.detail), failed: true });
      return;
    }
    setMessage({ id: applicationId, text: "Visa case started.", failed: false });
    loadChecklist(applicationId);
    router.refresh();
  }

  async function advance(applicationId: string, visaId: string, toStatus: string) {
    setBusyId(applicationId);
    setMessage(null);
    const response = await fetch(`/api/v1/workflows/overseas/visa/${visaId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: toStatus }),
    });
    const data = await response.json().catch(() => ({}));
    setBusyId(null);
    if (!response.ok) {
      setMessage({ id: applicationId, text: detailMessage(data.detail), failed: true });
      return;
    }
    setMessage({ id: applicationId, text: "Visa case advanced.", failed: false });
    loadChecklist(applicationId);
    router.refresh();
  }

  if (applications === null) {
    return (
      <div className="action-card">
        <h3>Visa Cases</h3>
        <p className="muted">Loading your assigned applications…</p>
      </div>
    );
  }

  if (applications.length === 0) {
    return (
      <div className="action-card">
        <h3>Visa Cases</h3>
        <p className="muted">No applications are assigned to you yet.</p>
      </div>
    );
  }

  const disclaimer = Object.values(statuses).find((s) => s.disclaimer)?.disclaimer || DEFAULT_DISCLAIMER;

  return (
    <div className="action-card">
      <h3>Visa Cases</h3>
      <div className="grid two" style={{ marginTop: 16 }}>
        {applications.map((row) => {
          const checklist = checklists[row.id];
          const status = statuses[row.id];
          const currentIndex = checklist?.status ? STAGES.indexOf(checklist.status) : -1;
          const nextStages = STAGES.slice(currentIndex + 1);
          return (
            <div className="card" key={row.id}>
              <h4>{row.student}</h4>
              <p className="muted" style={{ fontSize: 13 }}>{row.university}</p>
              {!checklist ? (
                <p className="muted" style={{ fontSize: 13 }}>Loading…</p>
              ) : !checklist.exists ? (
                <form className="form" onSubmit={(event) => startCase(event, row.id)}>
                  <div className="field">
                    <label htmlFor={`checklist-${row.id}`}>Checklist items (comma separated)</label>
                    <input id={`checklist-${row.id}`} name="checklist" placeholder="Passport, Offer letter, Financial evidence" required />
                  </div>
                  <button className="btn small" disabled={busyId === row.id}>
                    {busyId === row.id ? "Starting…" : "Start visa case"}
                  </button>
                </form>
              ) : (
                <>
                  <span className="badge">{label(checklist.status || "")}</span>
                  {status?.tracking_reference && <p className="muted" style={{ fontSize: 13 }}>Tracking reference: {status.tracking_reference}</p>}
                  {status?.appointment_date && <p className="muted" style={{ fontSize: 13 }}>Appointment: {status.appointment_date}</p>}
                  <ul className="list-clean" style={{ marginTop: 10 }}>
                    {checklist.checklist.map((item) => (
                      <li key={item.item}>{item.item} — <span className="muted">{item.verification_status.replaceAll("_", " ")}</span></li>
                    ))}
                  </ul>
                  {nextStages.length > 0 && (
                    <div style={{ marginTop: 8 }}>
                      {nextStages.map((stage) => (
                        <button key={stage} className="btn small" style={{ marginRight: 6, marginTop: 6 }} disabled={busyId === row.id} onClick={() => advance(row.id, checklist.id!, stage)}>
                          Advance to {label(stage)}
                        </button>
                      ))}
                    </div>
                  )}
                </>
              )}
              {message?.id === row.id && (
                <div className={message.failed ? "form-error" : "form-message"} role="status" aria-live="polite" style={{ marginTop: 8, fontSize: 13 }}>
                  {message.text}
                </div>
              )}
            </div>
          );
        })}
      </div>
      <p className="muted" style={{ marginTop: 16, fontSize: 13 }}>{disclaimer}</p>
    </div>
  );
}
