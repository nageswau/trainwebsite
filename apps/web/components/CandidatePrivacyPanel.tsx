"use client";

import { useState } from "react";

import LocalTime from "@/components/LocalTime";
import { sendJson } from "@/lib/apiErrors";
import { ERASURE_URL, type ErasureRequest, PRIVACY_URL, type PrivacyState } from "@/lib/candidatePortal";

// hrc-035 (DEC-SCOPE-396 K3/K5/K6): asking for the data to be deleted -- a confirm step, then the HR Manager decides. The open request is
// shown instead of the button; a rejection shows its reason and lets the candidate ask again.
function DeleteMyData({ erasure, onChange }: { erasure: ErasureRequest | null; onChange: (next: PrivacyState) => void }) {
  const [confirming, setConfirming] = useState(false);
  const [understood, setUnderstood] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const open = erasure?.status === "in_progress";

  async function send() {
    if (busy || !understood) return;
    setBusy(true);
    setError("");
    const outcome = await sendJson(ERASURE_URL, "POST", {});
    setBusy(false);
    if (!outcome.ok) return setError((outcome.status ?? 0) >= 500 || !outcome.status ? "We couldn't send your request. Please try again." : outcome.message);
    setConfirming(false);
    setUnderstood(false);
    onChange(outcome.data as PrivacyState);
  }

  return (
    <section className="card" aria-labelledby="privacy-delete">
      <h3 id="privacy-delete">Delete my data</h3>
      <p className="muted">
        You can ask us to delete your candidate data. The HR Manager reviews each request. If it is approved, your profile details, resumes and
        documents are deleted, your account is closed, and your past applications are kept only without your name or contact details. A
        request waits while you have a job offer in progress.
      </p>
      {open && (
        <p className="form-message" role="status">
          Your request was sent on <LocalTime value={erasure.requested_at} time /> and is waiting for review.
        </p>
      )}
      {erasure?.status === "rejected" && (
        <p className="form-error" role="status">
          Your request from <LocalTime value={erasure.requested_at} /> was declined: {erasure.rejection_reason}
        </p>
      )}
      {error && <p className="form-error" role="alert">{error}</p>}
      {!open && !confirming && (
        <button className="btn secondary" type="button" onClick={() => setConfirming(true)}>Request deletion</button>
      )}
      {!open && confirming && (
        <div style={{ display: "grid", gap: 12 }}>
          <label style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
            <input type="checkbox" checked={understood} disabled={busy} onChange={(e) => setUnderstood(e.target.checked)} />
            <span>I understand that once approved this cannot be undone and I will no longer be able to sign in.</span>
          </label>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button className="btn" type="button" disabled={busy || !understood} onClick={() => void send()}>{busy ? "Sending…" : "Send deletion request"}</button>
            <button className="btn secondary" type="button" disabled={busy} onClick={() => { setConfirming(false); setUnderstood(false); setError(""); }}>Cancel</button>
          </div>
        </div>
      )}
    </section>
  );
}

// hrc-022 (DEC-SCOPE-386 C12): the consent the candidate gave, its history, and leaving or re-joining the candidate pool (the rec-010
// idiom). Each change adds a consent record server-side.
export default function CandidatePrivacyPanel({ initial }: { initial: PrivacyState }) {
  const [state, setState] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);

  async function change(optedIn: boolean) {
    if (busy) return;
    setBusy(true);
    setMessage(null);
    const outcome = await sendJson(PRIVACY_URL, "PUT", { opted_in: optedIn, consent_version: state.consent.version });
    setBusy(false);
    if (!outcome.ok) return setMessage({ text: (outcome.status ?? 0) >= 500 ? "We couldn't save your choice. Please try again." : outcome.message, failed: true });
    setState(outcome.data as PrivacyState);
    setMessage({ text: optedIn ? "You are back in the candidate pool." : "You have left the candidate pool. Recruiters will no longer find you in searches.", failed: false });
  }

  return (
    <div className="grid" style={{ gap: 18 }}>
      <section className="card" aria-labelledby="privacy-consent">
        <h3 id="privacy-consent">Candidate pool consent</h3>
        <p>
          Status: <span className={state.opted_in ? "status" : "status pending"}>{state.opted_in ? "In the candidate pool" : "Not in the candidate pool"}</span>
        </p>
        <blockquote className="muted" style={{ margin: "0 0 16px", paddingLeft: 12, borderLeft: "3px solid var(--line)" }}>{state.consent.text}</blockquote>
        {message && <p className={message.failed ? "form-error" : "form-message"} role={message.failed ? "alert" : "status"}>{message.text}</p>}
        <button className={state.opted_in ? "btn secondary" : "btn"} type="button" disabled={busy} onClick={() => void change(!state.opted_in)}>
          {busy ? "Saving…" : state.opted_in ? "Leave the candidate pool" : "Join the candidate pool"}
        </button>
      </section>
      <DeleteMyData erasure={state.erasure ?? null} onChange={(next) => setState(next)} />
      <section className="card" aria-labelledby="privacy-history">
        <h3 id="privacy-history">Consent history</h3>
        {state.history.length === 0 ? <p className="muted">No consent recorded yet.</p> : (
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {state.history.map((entry, i) => (
              <li key={`${entry.created_at}-${i}`}>
                {entry.action === "opt_in" ? "Joined the pool" : "Left the pool"} · <LocalTime value={entry.created_at} time /> · wording {entry.consent_version}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
