"use client";

import { useState } from "react";

import LocalTime from "@/components/LocalTime";
import { sendJson } from "@/lib/apiErrors";
import { PRIVACY_URL, type PrivacyState } from "@/lib/candidatePortal";

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
