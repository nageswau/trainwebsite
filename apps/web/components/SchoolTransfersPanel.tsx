"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { formatDate } from "@/lib/formatDate";
import SchoolIncomingTransferForm from "@/components/SchoolIncomingTransferForm";
import { detailMessage, isPage, isRequestBody, type Page } from "@/lib/apiErrors";
import { STATUS_CLASS, STATUS_LABEL, type TransferRequest } from "@/lib/transfers";

// ENH-005 -- the coordinator's own filed requests (spec §5.2, §7.1). The first page (pending) is read on the server, so first paint has
// no spinner. A filter change replaces the rows behind a skeleton (the old rows would answer a different question); "Load more" appends
// and keeps what is on screen. A not-yet-approved incoming row shows the Student ID only -- the server has already nulled the rest.
const LIMIT = 25;
const FILTERS = [["pending", "Pending review"], ["all", "All"], ["approved", "Approved"], ["rejected", "Rejected"], ["cancelled", "Cancelled"]] as const;
type Filter = (typeof FILTERS)[number][0];
type Alert = { text: string; expired?: boolean; retry?: boolean };

function rowTitle(r: TransferRequest) {
  return r.student_name ?? `Student ID ${r.student_code}`;
}

export default function SchoolTransfersPanel({ initial }: { initial: Page<TransferRequest> }) {
  const [status, setStatus] = useState<Filter>("pending");
  const [items, setItems] = useState(initial.items);
  const [total, setTotal] = useState(initial.total);
  const [loading, setLoading] = useState<"filter" | "more" | null>(null);
  const [alert, setAlert] = useState<Alert | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  const alertRef = useRef<HTMLDivElement>(null);
  const messageRef = useRef<HTMLDivElement>(null);
  const cancelling = useRef(false); // `busyId` is state: two clicks in one task both see null (found by the browser QA)

  useEffect(() => {
    if (alert) alertRef.current?.focus();
  }, [alert]);
  useEffect(() => () => controller.current?.abort(), []);

  // mode "filter": replace behind a skeleton. "more": append. "refresh": replace in place (after a new request was filed).
  async function load(next: Filter, offset: number, mode: "filter" | "more" | "refresh") {
    controller.current?.abort();
    const abort = (controller.current = new AbortController());
    setAlert(null);
    setLoading(mode === "refresh" ? null : mode);
    try {
      const response = await fetch(`/api/v1/school/transfer-requests?status=${next}&limit=${LIMIT}&offset=${offset}`, { signal: abort.signal });
      const data = await response.json().catch(() => null);
      if (response.status === 401) return setAlert({ text: "Your session has expired. ", expired: true });
      if (!response.ok || !isPage<TransferRequest>(data)) return setAlert({ text: "Could not load transfer requests.", retry: true });
      setItems((prev) => (mode === "more" ? [...prev, ...data.items] : data.items));
      setTotal(data.total);
    } catch (error) {
      if ((error as Error).name !== "AbortError") setAlert({ text: "Could not load transfer requests.", retry: true });
    } finally {
      if (!abort.signal.aborted) setLoading(null);
    }
  }

  function changeStatus(next: Filter) {
    setStatus(next);
    setMessage(null);
    void load(next, 0, "filter");
  }

  async function cancel(row: TransferRequest) {
    if (cancelling.current) return;
    cancelling.current = true;
    setBusyId(row.id);
    setMessage(null);
    setAlert(null);
    let response: Response;
    try {
      response = await fetch(`/api/v1/school/transfer-requests/${row.id}/cancel`, { method: "POST" });
    } catch {
      cancelling.current = false;
      setBusyId(null);
      return setAlert({ text: "The cancel did not complete. Check your connection and try again." });
    }
    const data = await response.json().catch(() => null);
    cancelling.current = false;
    setBusyId(null);
    if (response.status === 401) return setAlert({ text: "Your session has expired. ", expired: true });
    if (!response.ok) return setAlert({ text: detailMessage(data?.detail) });
    // A 2xx that is not the request (a proxy page, an empty body) does not show it was cancelled; say so and offer a re-read (browser QA N2).
    if (!isRequestBody(data)) return setAlert({ text: "The cancel could not be confirmed. Reload the list to see where the request stands.", retry: true });
    setItems((prev) => (status === "pending" ? prev.filter((r) => r.id !== row.id) : prev.map((r) => (r.id === row.id ? { ...r, ...data } : r))));
    if (status === "pending") setTotal((t) => t - 1);
    setMessage("Request cancelled.");
    requestAnimationFrame(() => messageRef.current?.focus()); // the row (and its button) is gone: keep focus in this panel
  }

  const skeleton = loading === "filter";
  return (
    <div className="portal-content">
      <div className="card">
        <h2>Transfer requests</h2>
        <p className="muted">Requests your school has filed. An admin reviews each one; nothing changes until it is approved.</p>
        <div className="table-controls">
          <div>
            <label htmlFor="transfer-status">Status</label>
            <select id="transfer-status" className="select" value={status} disabled={loading !== null} onChange={(e) => changeStatus(e.target.value as Filter)}>
              {FILTERS.map(([value, text]) => <option key={value} value={value}>{text}</option>)}
            </select>
          </div>
        </div>
        <div ref={messageRef} tabIndex={-1} role="status" aria-live="polite">{message && <div className="form-message">{message}</div>}</div>
        {alert && (
          <div ref={alertRef} tabIndex={-1} className="form-error" role="alert">
            {alert.text}
            {alert.expired && <Link href="/overseas/login">Sign in again</Link>}
            {alert.retry && <button type="button" className="btn small secondary" onClick={() => void load(status, 0, "filter")}>Try again</button>}
          </div>
        )}
        {!skeleton && items.length === 0 && !alert ? (
          <div className="empty">
            {status === "pending" ? (
              <>
                <h3>No pending requests.</h3>
                <p>To move a student out, open their page and choose “Request a transfer”. To bring a student in, use the form below.</p>
                <Link className="btn secondary small" href="/school/coordinator/students">Go to the student roster</Link>
              </>
            ) : (
              <>
                <h3>{status === "all" ? "No transfer requests yet." : `No ${status} requests.`}</h3>
                <button type="button" className="btn secondary small" onClick={() => changeStatus("pending")}>Show pending</button>
              </>
            )}
          </div>
        ) : (
          <>
            <p className="muted" aria-live="polite">Showing {items.length} of {total}</p>
            <ul className="link-list" role="list" aria-label="Transfer requests" aria-busy={loading !== null}>
              {skeleton ? [0, 1, 2].map((i) => <li key={i} aria-hidden="true"><div className="skeleton-line" style={{ width: "100%" }} /></li>) : items.map((r) => (
                <li key={r.id}>
                  <div className="who">
                    <strong>{rowTitle(r)}</strong>
                    {r.direction === "outgoing" || r.student_name ? (
                      <span>{r.student_code} · {r.direction === "outgoing" ? `to ${r.to_school.name}` : `from ${r.from_school?.name ?? ""}`}</span>
                    ) : (
                      <span>Student details are shown once approved.</span>
                    )}
                    {r.decision_note && <span>Admin note: {r.decision_note}</span>}
                  </div>
                  <div className="meta">
                    <span className={STATUS_CLASS[r.status]}>{STATUS_LABEL[r.status]}</span>
                    <span className="muted">{formatDate(r.created_at)}</span>
                    {r.status === "pending" && (
                      <button type="button" className="btn small secondary" disabled={busyId === r.id} aria-label={`Cancel request for ${rowTitle(r)}`} onClick={() => void cancel(r)}>
                        {busyId === r.id ? "Cancelling…" : "Cancel"}
                      </button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
            {!skeleton && items.length < total && (
              <button type="button" className="btn secondary small" disabled={loading !== null} onClick={() => void load(status, items.length, "more")}>{loading === "more" ? "Loading…" : "Load more"}</button>
            )}
          </>
        )}
      </div>
      <div className="card">
        <SchoolIncomingTransferForm onSubmitted={() => void load(status, 0, "refresh")} />
      </div>
    </div>
  );
}
