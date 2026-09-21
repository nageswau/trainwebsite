"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import AdminTransferRow, { type Decision, type Failure } from "@/components/AdminTransferRow";
import { isPage } from "@/lib/apiErrors";
import type { AdminTransferRequest } from "@/lib/transfers";

// ENH-005 -- the admin's transfer queue (spec §5.3, §7.1). Loaded after first paint, like AdminExpiredLinksPanel, so nothing else on the
// page is blocked. Pending by default; a decision removes the row and announces the outcome in a live region that is mounted from the
// start (so screen readers announce it) and takes focus, because the row and its button are gone.
const LIMIT = 25;
const FILTERS = [["pending", "Pending review"], ["all", "All"], ["approved", "Approved"], ["rejected", "Rejected"], ["cancelled", "Cancelled"]] as const;
type Filter = (typeof FILTERS)[number][0];

export default function AdminSchoolTransferPanel() {
  const [status, setStatus] = useState<Filter>("pending");
  const [items, setItems] = useState<AdminTransferRequest[] | null>(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState<"first" | "more" | null>("first");
  const [alert, setAlert] = useState<Failure | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  const alertRef = useRef<HTMLDivElement>(null);
  const messageRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async (next: Filter, offset: number, mode: "first" | "more" | "refresh") => {
    controller.current?.abort();
    const abort = (controller.current = new AbortController());
    setLoading(mode === "refresh" ? null : mode);
    if (mode === "first") setItems(null);
    try {
      const response = await fetch(`/api/v1/overseas-admin/school-transfer-requests?status=${next}&limit=${LIMIT}&offset=${offset}`, { signal: abort.signal });
      const data = await response.json().catch(() => null);
      if (response.status === 401) return setAlert({ text: "Your session has expired. ", expired: true });
      if (!response.ok || !isPage<AdminTransferRequest>(data)) return setAlert({ text: "Could not load transfer requests.", refetch: true });
      setAlert((current) => (current?.refetch && current.text.startsWith("Could not load") ? null : current));
      setItems((prev) => (mode === "more" && prev ? [...prev, ...data.items] : data.items));
      setTotal(data.total);
    } catch (error) {
      if ((error as Error).name !== "AbortError") setAlert({ text: "Could not load transfer requests.", refetch: true });
    } finally {
      if (!abort.signal.aborted) setLoading(null);
    }
  }, []);

  useEffect(() => {
    void load("pending", 0, "first");
    return () => controller.current?.abort();
  }, [load]);
  useEffect(() => {
    if (alert) alertRef.current?.focus();
  }, [alert]);

  const onDecided = useCallback(({ request, message: text }: Decision) => {
    setAlert(null);
    setMessage(text);
    setItems((prev) => (prev ? (status === "pending" ? prev.filter((row) => row.id !== request.id) : prev.map((row) => (row.id === request.id ? request : row))) : prev));
    if (status === "pending") setTotal((t) => Math.max(0, t - 1));
    requestAnimationFrame(() => messageRef.current?.focus());
  }, [status]);
  const onFailure = useCallback((failure: Failure) => {
    setMessage(null);
    setAlert(failure);
    if (failure.refetch) void load(status, 0, "refresh"); // already decided, stale, or the lock was busy: show the queue as it now is
  }, [load, status]);

  function changeStatus(next: Filter) {
    setStatus(next);
    setMessage(null);
    setAlert(null);
    void load(next, 0, "first");
  }

  return (
    <div className={`action-card${items && items.length > 0 ? " wide" : ""}`}>
      <div>
        <h3>Transfer requests{total > 0 ? ` (${total})` : ""}</h3>
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>Coordinators ask; you decide. Approving moves the student in one step.</p>
      </div>
      <div className="table-controls">
        <div>
          <label htmlFor="admin-transfer-status">Status</label>
          <select id="admin-transfer-status" className="select" value={status} disabled={loading !== null} onChange={(e) => changeStatus(e.target.value as Filter)}>
            {FILTERS.map(([value, text]) => <option key={value} value={value}>{text}</option>)}
          </select>
        </div>
      </div>
      <div ref={messageRef} tabIndex={-1} role="status" aria-live="polite">{message && <div className="form-message">{message}</div>}</div>
      {alert && (
        <div ref={alertRef} tabIndex={-1} className="form-error" role="alert">
          <p style={{ margin: 0 }}>{alert.text}{alert.expired && <Link href="/overseas/login"> Sign in again</Link>}</p>
          {alert.text.startsWith("Could not load") && <button type="button" className="btn small secondary" style={{ marginTop: 8 }} onClick={() => void load(status, 0, "first")}>Try again</button>}
        </div>
      )}
      {items === null && !alert ? (
        <div aria-busy="true">
          <p className="muted" style={{ margin: "0 0 8px" }}>Loading transfer requests…</p>
          <div className="skeleton-line" aria-hidden="true" />
        </div>
      ) : items !== null && items.length === 0 && !alert ? (
        <div className="empty">
          <h3>{status === "pending" ? "No pending transfer requests." : status === "all" ? "No transfer requests yet." : `No ${status} requests.`}</h3>
          {status !== "pending" && <button type="button" className="btn secondary small" onClick={() => changeStatus("pending")}>Show pending</button>}
        </div>
      ) : items !== null && items.length > 0 ? (
        <>
          <p className="muted" aria-live="polite">Showing {items.length} of {total}</p>
          <ul className="link-list" role="list" aria-label="Transfer requests">
            {items.map((row) => <AdminTransferRow key={row.id} request={row} onDecided={onDecided} onFailure={onFailure} />)}
          </ul>
          {items.length < total && <button type="button" className="btn secondary small" disabled={loading !== null} onClick={() => void load(status, items.length, "more")}>{loading === "more" ? "Loading…" : "Load more"}</button>}
        </>
      ) : null}
    </div>
  );
}
