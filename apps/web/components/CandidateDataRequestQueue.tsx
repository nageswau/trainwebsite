"use client";

import { useState } from "react";

import LocalTime from "@/components/LocalTime";
import { sendJson } from "@/lib/apiErrors";
import { DATA_REQUESTS_URL, type DataRequestRow, REASON_LIMIT, STATUS_LABEL } from "@/lib/candidateDataRequests";

// hrc-035 (DEC-SCOPE-396 K5/K7): candidates' "delete my data" requests, oldest first. Approve anonymises the candidate (after a confirm);
// reject needs a reason the candidate will read. A request held by an offer in progress cannot be approved until the offer is decided.
function RequestCard({ row, onDecided }: { row: DataRequestRow; onDecided: (row: DataRequestRow, text: string) => void }) {
  const [mode, setMode] = useState<"" | "approve" | "reject">("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const who = row.candidate ? `${row.candidate.name} (${row.candidate.candidate_code})` : "A candidate account with no candidate record";

  async function decide(decision: "approve" | "reject") {
    if (busy) return;
    if (decision === "reject" && !reason.trim()) return setError("Give the candidate a reason for keeping their data.");
    setBusy(true);
    setError("");
    const outcome = await sendJson(`${DATA_REQUESTS_URL}/${encodeURIComponent(row.id)}/decision`, "POST", decision === "reject" ? { decision, reason: reason.trim() } : { decision });
    setBusy(false);
    if (!outcome.ok) return setError(!outcome.status || outcome.status >= 500 ? "The decision was not saved. Please try again." : outcome.message);
    onDecided(outcome.data as DataRequestRow, decision === "approve" ? `${who}'s data was deleted.` : `${who}'s request was declined.`);
  }

  const id = `dr-${row.id}`;
  return (
    <li className="action-card" aria-labelledby={`${id}-name`} style={{ display: "grid", gap: 8 }}>
      <h4 id={`${id}-name`} style={{ margin: 0, overflowWrap: "anywhere" }}>{who}</h4>
      <p className="muted" style={{ margin: 0, overflowWrap: "anywhere" }}>
        {row.candidate?.email ? <>{row.candidate.email} · </> : null}Requested <LocalTime value={row.requested_at} time /> · {row.open_applications} open application{row.open_applications === 1 ? "" : "s"}
      </p>
      {row.held && <p className="status pending" style={{ margin: 0 }}>On hold: an offer is in progress. Decide the offer first.</p>}
      {error && <p className="form-error" role="alert">{error}</p>}
      {mode === "" && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button className="btn" type="button" disabled={row.held} onClick={() => setMode("approve")}>Approve deletion</button>
          <button className="btn secondary" type="button" onClick={() => setMode("reject")}>Decline…</button>
        </div>
      )}
      {mode === "approve" && (
        <div style={{ display: "grid", gap: 8 }}>
          <p style={{ margin: 0 }}>This deletes the candidate&apos;s details, resumes and documents and closes their account. It cannot be undone.</p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button className="btn" type="button" disabled={busy} onClick={() => void decide("approve")}>{busy ? "Deleting…" : "Delete the data"}</button>
            <button className="btn secondary" type="button" disabled={busy} onClick={() => setMode("")}>Cancel</button>
          </div>
        </div>
      )}
      {mode === "reject" && (
        <div style={{ display: "grid", gap: 8 }}>
          <div className="field">
            <label htmlFor={`${id}-reason`}>Reason shown to the candidate</label>
            <textarea id={`${id}-reason`} rows={3} maxLength={REASON_LIMIT} value={reason} disabled={busy} onChange={(e) => setReason(e.target.value)} />
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button className="btn" type="button" disabled={busy} onClick={() => void decide("reject")}>{busy ? "Saving…" : "Decline the request"}</button>
            <button className="btn secondary" type="button" disabled={busy} onClick={() => { setMode(""); setError(""); }}>Cancel</button>
          </div>
        </div>
      )}
    </li>
  );
}

export default function CandidateDataRequestQueue({ open, decided }: { open: DataRequestRow[]; decided: DataRequestRow[] }) {
  const [rows, setRows] = useState(open);
  const [done, setDone] = useState(decided);
  const [message, setMessage] = useState("");

  function decidedRow(row: DataRequestRow, text: string) {
    setRows((current) => current.filter((r) => r.id !== row.id));
    setDone((current) => [row, ...current.filter((r) => r.id !== row.id)]);
    setMessage(text);
  }

  return (
    <div className="grid" style={{ gap: 18 }}>
      <section className="card" aria-labelledby="dr-open">
        <h3 id="dr-open">Waiting for a decision</h3>
        {message && <p className="form-message" role="status">{message}</p>}
        {rows.length === 0 ? <p className="muted">No deletion requests waiting.</p> : (
          <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 12 }}>
            {rows.map((row) => <RequestCard key={row.id} row={row} onDecided={decidedRow} />)}
          </ul>
        )}
      </section>
      <section className="card" aria-labelledby="dr-decided">
        <h3 id="dr-decided">Decided</h3>
        {done.length === 0 ? <p className="muted">No decisions yet.</p> : (
          <ul style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 6 }}>
            {done.map((row) => (
              <li key={row.id} style={{ overflowWrap: "anywhere" }}>
                <strong>{STATUS_LABEL[row.status]}</strong> · {row.candidate ? row.candidate.candidate_code : "No candidate record"}
                {row.decided_at && <> · <LocalTime value={row.decided_at} time /></>}
                {row.rejection_reason && <> · {row.rejection_reason}</>}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
