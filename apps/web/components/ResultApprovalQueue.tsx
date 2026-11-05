"use client";
import Link from "next/link";
import { type FormEvent, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { formatSchoolDateTime } from "@/lib/formatDate";
import {
  MESSAGE_MAX, releaseUrl, type ResultQueue, type ResultRow, type ResultSettings, type ResultState, RESULTS_PATH, RESULTS_URL, STATES,
} from "@/lib/interviewResults";

// hrc-030 (DEC-SCOPE-409 R11/R13): the approver's results -- the ones waiting, oldest first, each with the message the candidate will read
// and a Publish button; and the published ones. A published row leaves the waiting list (the API's answer is the truth). super_admin also
// switches auto-release on or off (R4).

function PublishForm({ row, onDone }: { row: ResultRow; onDone: (text: string) => void }) {
  const [message, setMessage] = useState(row.candidate_message);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const field = `result-${row.id}-message`;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    const outcome = await sendJson(releaseUrl(row.id), "POST", { candidate_message: message.trim() || null });
    setBusy(false);
    if (outcome.ok) onDone(`Result published to ${row.candidate.name} (${row.candidate.code}).`);
    else setError(outcome.message);
  }

  return (
    <form onSubmit={submit} style={{ display: "grid", gap: 6, marginTop: 8 }}>
      <label htmlFor={field}>Message to the candidate</label>
      <textarea id={field} value={message} maxLength={MESSAGE_MAX} rows={3} onChange={(e) => setMessage(e.target.value)}
        aria-describedby={`${field}-hint`} disabled={busy} />
      <span id={`${field}-hint`} className="muted" style={{ fontSize: 13 }}>
        The candidate sees this message and the outcome only. Feedback, scores and notes are never shared. Left blank, the standard wording is sent.
      </span>
      {error && <p className="form-error" role="alert" style={{ margin: 0 }}>{error}</p>}
      <div><button type="submit" className="btn small" disabled={busy}>{busy ? "Publishing…" : "Publish result"}</button></div>
    </form>
  );
}

function Settings({ initial }: { initial: ResultSettings }) {
  const [auto, setAuto] = useState(initial.auto_release);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);

  async function toggle(next: boolean) {
    const previous = auto;
    setAuto(next);
    setBusy(true);
    setMessage(null);
    const outcome = await sendJson(`${RESULTS_URL}/settings`, "PUT", { auto_release: next });
    setBusy(false);
    const saved = outcome.ok ? (outcome.data as ResultSettings | null)?.auto_release : undefined;
    if (typeof saved === "boolean") {
      setAuto(saved);
      setMessage({ text: saved ? "Results are now published automatically." : "Results now wait for approval.", failed: false });
    } else {
      setAuto(previous);
      setMessage({ text: outcome.ok ? "Unable to save the setting." : outcome.message, failed: true });
    }
  }

  return (
    <section className="action-card wide" aria-labelledby="result-settings">
      <h3 id="result-settings">How results are released</h3>
      <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <input type="checkbox" checked={auto} disabled={!initial.can_edit || busy} onChange={(e) => void toggle(e.target.checked)} />
        Publish interview results to candidates automatically, without approval
      </label>
      <p className="muted" style={{ margin: 0 }}>
        {initial.can_edit ? "Turning this on never publishes results already waiting." : "Only a super admin can change this setting."}
      </p>
      <div role="status" aria-live="polite" className={message ? (message.failed ? "form-error" : "form-message") : undefined}>{message?.text}</div>
    </section>
  );
}

export default function ResultApprovalQueue({ state, page, settings }: { state: ResultState; page: ResultQueue; settings: ResultSettings }) {
  const [rows, setRows] = useState(page.items);
  const [notice, setNotice] = useState<string | null>(null);
  const done = page.items.length - rows.length;
  const pending = state === "pending_approval";

  return (
    <>
      <nav aria-label="Result lists" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {STATES.map((s) => (
          <Link key={s.key} href={`${RESULTS_PATH}?state=${s.key}`} className={`btn small${s.key === state ? "" : " secondary"}`}
            aria-current={s.key === state ? "page" : undefined}>
            {s.label} ({s.key === "pending_approval" ? page.counts.pending_approval - done : page.counts.released + (pending ? done : 0)})
          </Link>
        ))}
      </nav>
      <div id="result-notice" tabIndex={-1} role="status" aria-live="polite" className={notice ? "form-message" : undefined}>{notice}</div>
      <section className="action-card wide" aria-labelledby="result-list">
        <h3 id="result-list">{pending ? "Waiting for approval" : "Published results"}</h3>
        {rows.length === 0 ? (
          <p style={{ margin: 0 }}>{pending ? "No interview results are waiting for approval." : "No results have been published yet."}</p>
        ) : (
          <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 16 }}>
            {rows.map((row) => (
              <li key={row.id} className="action-card" style={{ margin: 0, overflowWrap: "anywhere" }} aria-labelledby={`result-${row.id}-title`}>
                <div className="eyebrow">{row.interview.code} · {row.requirement.code}</div>
                <h4 id={`result-${row.id}-title`} style={{ margin: "4px 0" }}>
                  {row.candidate.name} ({row.candidate.code}) <span className="badge">{row.outcome_label}</span>
                  {row.is_final && <span className="badge" style={{ marginLeft: 6 }}>Final decision</span>}
                </h4>
                <p style={{ margin: 0 }}>{row.interview.round} · {row.requirement.title} · {row.company.name}</p>
                <p className="muted" style={{ margin: 0, fontSize: 13 }}>
                  Decided by {row.decided_by?.full_name ?? "the system"} on {formatSchoolDateTime(row.decided_at)}
                  {row.released_at && ` · Published ${row.release_mode === "auto" ? "automatically " : ""}on ${formatSchoolDateTime(row.released_at)}`}
                </p>
                {pending && row.can_release ? (
                  <PublishForm row={row} onDone={(text) => {
                    setRows((current) => current.filter((r) => r.id !== row.id));
                    setNotice(text);
                    document.getElementById("result-notice")?.focus();
                  }} />
                ) : (
                  <>
                    <p style={{ margin: "8px 0 0", whiteSpace: "pre-line" }}><strong>Message:</strong> {row.candidate_message}</p>
                    {pending && <p className="muted" style={{ margin: "8px 0 0" }}>You recorded this decision, so another approver must publish it.</p>}
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
        {page.total > page.items.length && <p className="muted">Showing {page.items.length} of {page.total}.</p>}
      </section>
      <Settings initial={settings} />
    </>
  );
}
