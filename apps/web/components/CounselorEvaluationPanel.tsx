"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import ApplicationOutcomeForm from "./ApplicationOutcomeForm";
import ApplicationSubStatusForm from "./ApplicationSubStatusForm";
import ReopenOutcomeButton from "./ReopenOutcomeButton";
import { isTerminal, outcomeChoices } from "@/lib/applicationOutcome";

type ApplicationRow = { id: string; student: string; university: string; reference: string | null; status: string; sub_status?: string | null; sub_status_label?: string | null; next_action: string | null; is_agency?: boolean; outcome?: string | null; outcome_label?: string | null; outcome_summary?: string | null };

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
  const [subStatusId, setSubStatusId] = useState<string | null>(null); // ccrm-014: the card whose sub-status form is open
  const [outcomeId, setOutcomeId] = useState<string | null>(null); // ccrm-015: the card whose outcome form is open
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
          // AGN-023 (DEC-SCOPE-090 H12): an agency application is enrolled by the agency's Master only (DEC-SCOPE-054); not offered here.
          // ccrm-015 (O2): a closed application takes no stage write; on hold pauses them until resumed.
          const closed = row.status === "withdrawn" || isTerminal(row.outcome);
          const paused = closed || row.outcome === "on_hold";
          const nextStages = paused ? [] : STAGES.slice(currentIndex + 1).filter((stage) => !(row.is_agency && stage === "enrolled"));
          const saved = (text: string) => {
            setMessage({ id: row.id, text, failed: false });
            setOutcomeId(null);
            router.refresh();
            load();
          };
          return (
            <div className="card" key={row.id}>
              {/* QA-01: the two badges wrap together without an indent */}
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                <span className="badge">{label(row.status)}</span>
                {row.sub_status_label && <span className="badge">{row.sub_status_label}</span>}
                {row.outcome_label && <span className={closed ? "status error" : "status pending"}>{row.outcome_label}</span>}
              </div>
              <h4 style={{ marginTop: 10 }}>{row.student}</h4>
              <p className="muted" style={{ fontSize: 13 }}>{row.university}</p>
              {row.next_action && <p className="muted" style={{ fontSize: 13 }}>{row.next_action}</p>}
              {row.is_agency && <p className="muted" style={{ fontSize: 13 }}>Enrollment is confirmed by the agency.</p>}
              {row.outcome_summary && <p style={{ fontSize: 13 }}>{row.outcome_summary}</p>}
              {paused ? (
                <p className="muted" style={{ fontSize: 13 }}>{closed ? "This application is closed -- only the Overseas Admin can reopen it." : "On hold -- resume it to change its stage."}</p>
              ) : nextStages.length === 0 ? (
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
              {!paused &&
                (subStatusId === row.id ? (
                  <ApplicationSubStatusForm
                    id={row.id}
                    url={`/api/v1/workflows/overseas/applications/${row.id}/sub-status`}
                    stage={row.status}
                    current={row.sub_status}
                    // AGN-023 H12 / ccrm-014 SS4: the agency enrols its own applications
                    maxStage={row.is_agency ? "status_tracking" : "enrolled"}
                    onSaved={(_data, text) => {
                      setMessage({ id: row.id, text: `${text} The student has been notified.`, failed: false });
                      setSubStatusId(null);
                      router.refresh();
                      load();
                    }}
                    onFailed={(text) => setMessage({ id: row.id, text, failed: true })}
                    onCancel={() => setSubStatusId(null)}
                  />
                ) : (
                  <button className="btn ghost small" style={{ display: "block", marginTop: 8 }} onClick={() => (setSubStatusId(row.id), setMessage(null))}>
                    Update sub-status
                  </button>
                ))}
              {(row.outcome === "on_hold" || row.outcome === "deferred") && (
                <div style={{ marginTop: 8 }}>
                  <ReopenOutcomeButton applicationId={row.id} action="Resume" onDone={saved} />
                </div>
              )}
              {outcomeChoices(row.status, row.outcome).length > 0 &&
                (outcomeId === row.id ? (
                  <ApplicationOutcomeForm
                    id={row.id}
                    stage={row.status}
                    outcome={row.outcome}
                    onSaved={(_data, text) => saved(`${text} The student has been notified.`)}
                    onFailed={(text) => setMessage({ id: row.id, text, failed: true })}
                    onCancel={() => setOutcomeId(null)}
                  />
                ) : (
                  <button className="btn ghost small" style={{ display: "block", marginTop: 8 }} onClick={() => (setOutcomeId(row.id), setMessage(null))}>
                    Record outcome
                  </button>
                ))}
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
