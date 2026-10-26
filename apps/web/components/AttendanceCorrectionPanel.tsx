"use client";

import { FormEvent, Fragment, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { formatDate } from "@/lib/formatDate";

type Row = { id: string; batch: string; session_date: string; status: string; correction_pending: boolean };

const STATUSES = ["present", "absent", "late", "excused"];
const label = (status: string) => status.charAt(0).toUpperCase() + status.slice(1);
const day = (value: string) => formatDate(value, false, "UTC"); // a session date, not a moment: never shift it by zone

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to submit the correction request.";
}

// nehn-023 (AC1): the student requests a correction from their own session row -- the record is picked, never typed.
export default function AttendanceCorrectionPanel() {
  const router = useRouter();
  const [rows, setRows] = useState<Row[] | null>(null);
  const [selected, setSelected] = useState<Row | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);
  const statusRef = useRef<HTMLSelectElement>(null);

  async function load() {
    try {
      const response = await fetch("/api/v1/workflows/it/student/attendance");
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(detailMessage(data.detail));
      setRows(data);
    } catch (error) {
      setRows([]);
      setFailed(true);
      setMessage(error instanceof Error ? error.message : "Unable to load your sessions.");
    }
  }

  useEffect(() => { void load(); }, []);
  useEffect(() => { if (selected) statusRef.current?.focus(); }, [selected]);

  function open(row: Row) {
    setSelected(row);
    setMessage("");
    setFailed(false);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const form = new FormData(event.currentTarget);
    const reason = String(form.get("reason") || "").trim();
    if (reason.length < 5) {
      setFailed(true);
      setMessage("Enter a reason of at least 5 characters.");
      return;
    }
    setBusy(true);
    setMessage("");
    setFailed(false);
    try {
      const response = await fetch("/api/v1/workflows/it/student/attendance-corrections", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ attendance_id: selected.id, requested_status: form.get("requested_status"), reason }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(detailMessage(data.detail));
      setSelected(null);
      setMessage("Correction request submitted.");
      await load();
      router.refresh();
    } catch (error) {
      setFailed(true);
      setMessage(error instanceof Error ? error.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }

  const feedback = message && <div className={failed ? "form-error" : "form-message"} role={failed ? "alert" : "status"} aria-live={failed ? "assertive" : "polite"}>{message}</div>;

  const form = selected && (
    <form className="form" aria-label="Correction request" onSubmit={submit}>
      <p><strong>{day(selected.session_date)} · {selected.batch}</strong> <span className="muted">(marked {selected.status})</span></p>
      <div className="field">
        <label htmlFor="correction-status">Correct status</label>
        <select ref={statusRef} id="correction-status" name="requested_status" required>
          {STATUSES.filter(status => status !== selected.status).map(status => <option key={status} value={status}>{label(status)}</option>)}
        </select>
      </div>
      <div className="field">
        <label htmlFor="correction-reason">Reason</label>
        <textarea id="correction-reason" name="reason" required maxLength={2000} />
      </div>
      {feedback}
      <div className="actions">
        <button className="btn small" disabled={busy}>{busy ? "Submitting…" : "Submit request"}</button>
        <button type="button" className="btn small secondary" onClick={() => { setSelected(null); setMessage(""); setFailed(false); }} disabled={busy}>Cancel</button>
      </div>
    </form>
  );

  return (
    <div className="action-card">
      <h3>Request correction</h3>
      <p className="muted">Pick the session that was marked wrongly. Your trainer is notified and you hear back when it is decided.</p>
      {!selected && feedback}
      {rows === null ? <p className="muted">Loading your sessions…</p> : rows.length === 0 ? (!failed && <p className="muted">No attendance has been recorded for you yet.</p>) : (
        <div className="table-wrap">
          <table className="table stack compact">
            <thead><tr><th scope="col">Date</th><th scope="col">Batch</th><th scope="col">Status</th><th scope="col">Correction</th></tr></thead>
            <tbody>
              {rows.map(row => (
                <Fragment key={row.id}>
                  <tr>
                    <th scope="row" data-label="Date">{day(row.session_date)}</th>
                    <td data-label="Batch">{row.batch}</td>
                    <td data-label="Status">{label(row.status)}</td>
                    <td data-label="Correction">{row.correction_pending ? <span className="status pending">Correction pending</span> : (
                      <button type="button" className="btn small secondary" aria-label={`Request correction for ${day(row.session_date)}, ${row.batch}`} aria-expanded={selected?.id === row.id} onClick={() => open(row)} disabled={busy}>Request correction</button>
                    )}</td>
                  </tr>
                  {/* QA-01: the form opens directly under its row, so on a phone the session stays in view. */}
                  {selected?.id === row.id && <tr><td colSpan={4} style={{ flexDirection: "column" }}>{form}</td></tr>}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
