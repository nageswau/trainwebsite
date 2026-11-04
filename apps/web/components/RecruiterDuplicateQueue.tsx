"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import LocalTime from "@/components/LocalTime";
import { isPage, sendRequest } from "@/lib/apiErrors";
import { CANDIDATES_PATH } from "@/lib/recruiterCandidates";
import { DUPLICATE_STATUSES, DUPLICATES_URL, SIGNAL_LABEL, mergePath, type DuplicatePair, type DuplicateSide, type DuplicateStatus } from "@/lib/recruiterDuplicates";

// hrc-014 (DEC-SCOPE-377 D2/D9): probable duplicates to review -- open pairs oldest first; "Review and merge" opens the side-by-side
// screen, "Not the same person" closes the pair for good. The API decides who may see it (`candidates.merge`); its refusal is shown.
const LIMIT = 50;
const EMPTY: Record<DuplicateStatus, string> = { open: "No probable duplicates to review.", dismissed: "No pairs marked as different people.", merged: "No merged pairs yet." };

function Person({ side }: { side: DuplicateSide }) {
  return (
    <div style={{ display: "grid", gap: 2 }}>
      <Link href={`${CANDIDATES_PATH}/${encodeURIComponent(side.id)}`} style={{ overflowWrap: "anywhere" }}>{side.name}</Link>
      <span className="muted" style={{ fontSize: 13, overflowWrap: "anywhere" }}>
        {side.candidate_code}{side.location ? ` · ${side.location}` : ""}{side.college ? ` · ${side.college}` : ""}{side.archived ? " · Archived" : ""}
      </span>
    </div>
  );
}

export default function RecruiterDuplicateQueue() {
  const [status, setStatus] = useState<DuplicateStatus>("open");
  const [pairs, setPairs] = useState<DuplicatePair[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const sending = useRef(false);

  const load = useCallback(async (which: DuplicateStatus) => {
    setPairs(null);
    setError("");
    const outcome = await sendRequest(`${DUPLICATES_URL}?${new URLSearchParams({ status: which, limit: String(LIMIT) })}`, { method: "GET" });
    if (!outcome.ok || !isPage<DuplicatePair>(outcome.data)) return setError(outcome.ok ? "Unable to load the duplicates." : outcome.message);
    setPairs(outcome.data.items);
    setTotal(outcome.data.total);
  }, []);
  useEffect(() => { void load(status); }, [load, status]);

  async function run(url: string, done: (data: Record<string, unknown>) => void) {
    if (sending.current) return;
    sending.current = true;
    setBusy(true);
    setNotice("");
    setError("");
    const outcome = await sendRequest(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    sending.current = false;
    setBusy(false);
    if (!outcome.ok) return setError(outcome.message);
    done(outcome.data);
  }

  const scan = () => run(`${DUPLICATES_URL}/scan`, (data) => {
    const created = Number(data.created ?? 0);
    setNotice(created ? `${created} new pair${created === 1 ? "" : "s"} to review.` : "No new probable duplicates found.");
    if (created && status === "open") void load("open");
  });
  const dismiss = (pair: DuplicatePair) => {
    if (!window.confirm(`${pair.candidate.name} (${pair.candidate.candidate_code}) and ${pair.other.name} (${pair.other.candidate_code}) are different people? They will not be suggested again.`)) return;
    void run(`${DUPLICATES_URL}/${encodeURIComponent(pair.id)}/dismiss`, () => {
      setPairs((list) => list?.filter((p) => p.id !== pair.id) ?? null);
      setTotal((n) => Math.max(0, n - 1));
      setNotice("Marked as not the same person.");
    });
  };

  return (
    <div style={{ display: "grid", gap: 12 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }} aria-label="Show">
          {DUPLICATE_STATUSES.map((s) => (
            <button key={s.key} type="button" className={s.key === status ? "btn small" : "btn secondary small"} aria-pressed={s.key === status} onClick={() => setStatus(s.key)}>
              {s.label}
            </button>
          ))}
        </div>
        <button type="button" className="btn secondary small" disabled={busy} onClick={() => void scan()}>{busy ? "Working…" : "Check the whole pool"}</button>
      </div>
      <div aria-live="polite">{notice && <p className="form-message" role="status" style={{ margin: 0 }}>{notice}</p>}</div>
      {error && <p className="form-error" role="alert" style={{ margin: 0 }}>{error}</p>}
      {pairs === null && !error && <p className="muted" role="status">Loading duplicates…</p>}
      {pairs !== null && pairs.length === 0 && <div className="action-card"><p style={{ margin: 0 }}>{EMPTY[status]}</p></div>}
      {pairs !== null && pairs.length > 0 && (
        <div style={{ overflowX: "auto" }}>
          <table className="table compact stack">
            <caption className="visually-hidden">Probable duplicate candidates</caption>
            <thead>
              <tr>
                <th scope="col">Candidate</th>
                <th scope="col">Possible duplicate</th>
                <th scope="col">Why</th>
                <th scope="col">{status === "open" ? "Found" : "Decided"}</th>
                {status === "open" && <th scope="col"><span className="visually-hidden">Actions</span></th>}
              </tr>
            </thead>
            <tbody>
              {pairs.map((pair) => (
                <tr key={pair.id}>
                  <td data-label="Candidate"><Person side={pair.candidate} /></td>
                  <td data-label="Possible duplicate"><Person side={pair.other} /></td>
                  <td data-label="Why">
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                      {pair.signals.map((signal) => <span key={signal} className="badge">{SIGNAL_LABEL[signal] ?? signal}</span>)}
                    </div>
                  </td>
                  <td data-label={status === "open" ? "Found" : "Decided"}>
                    <LocalTime value={status === "open" ? pair.created_at : pair.decided_at} />
                    {pair.decided_by && <span className="muted"> by {pair.decided_by.full_name}</span>}
                  </td>
                  {status === "open" && (
                    <td data-label="">
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                        <Link className="btn small" href={mergePath(pair.candidate.id, pair.other.candidate_code)}
                          aria-label={`Review and merge ${pair.candidate.name} and ${pair.other.name}`}>Review and merge</Link>
                        <button type="button" className="btn secondary small" disabled={busy} onClick={() => dismiss(pair)}
                          aria-label={`Not the same person: ${pair.candidate.name} and ${pair.other.name}`}>Not the same person</button>
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
          {total > pairs.length && <p className="muted" style={{ fontSize: 13 }}>Showing the first {pairs.length} of {total}. Review these to see more.</p>}
        </div>
      )}
    </div>
  );
}
