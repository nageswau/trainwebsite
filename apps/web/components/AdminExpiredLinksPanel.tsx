"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { refocus } from "@/lib/focus";
import { type Feedback, errorText, requestWelcomeLink, toneClass, welcomeLinkFeedback } from "@/lib/welcomeLink";

type ExpiredRow = { id: string; name: string; email: string; role: string };

// ENH-003 / DEC-SCOPE-019: admin-provisioned accounts whose 72-hour set-password link expired
// unused (division-scoped server-side). The list is fetched after first paint, so the dashboard's
// own content is never blocked by it. Loading / empty / error states are explicit; the outcome
// region is mounted from the start so screen readers announce Re-send results reliably.
export default function AdminExpiredLinksPanel() {
  const [rows, setRows] = useState<ExpiredRow[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const feedbackRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoadFailed(false);
    setRows(null);
    try {
      const response = await fetch("/api/v1/admin/users?provisioning_status=link_expired", { signal });
      if (!response.ok) throw new Error(String(response.status));
      setRows(await response.json());
    } catch (error) {
      if ((error as Error).name !== "AbortError") setLoadFailed(true);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  async function resend(row: ExpiredRow) {
    setBusyId(row.id);
    setFeedback(null);
    const { ok, data } = await requestWelcomeLink(row.id);
    setBusyId(null);
    if (!ok) {
      setFeedback({ text: errorText(data.detail, "Unable to re-send the link."), tone: "error" });
      refocus(`expired-resend-${row.id}`);
      return;
    }
    setFeedback(welcomeLinkFeedback(`New link created for ${row.name}.`, data));
    setRows((prev) => (prev ? prev.filter((r) => r.id !== row.id) : prev));
    // The row (and its button) is gone: keep keyboard focus in this panel and let the region announce.
    requestAnimationFrame(() => feedbackRef.current?.focus());
  }

  const count = rows?.length ?? 0;
  return (
    <div className={`action-card${count > 0 ? " wide" : ""}`}>
      <div>
        <h3>Expired set-password links{count > 0 ? ` (${count})` : ""}</h3>
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>Accounts whose emailed link expired before the user set a password.</p>
      </div>
      <div ref={feedbackRef} tabIndex={-1} role="status" aria-live="polite">
        {feedback && <div className={toneClass[feedback.tone]}>{feedback.text}</div>}
      </div>
      {loadFailed ? (
        <div className="form-error" role="alert">
          <p style={{ margin: 0 }}>Could not load expired links.</p>
          <button type="button" className="btn small secondary" style={{ marginTop: 8 }} onClick={() => void load()}>Try again</button>
        </div>
      ) : rows === null ? (
        <div aria-busy="true">
          <p className="muted" style={{ margin: "0 0 8px" }}>Loading expired links…</p>
          <div className="skeleton-line" aria-hidden="true" />
        </div>
      ) : rows.length === 0 ? (
        <p className="muted" style={{ margin: 0 }}>No expired links.</p>
      ) : (
        <ul className="link-list" role="list" aria-label="Accounts with an expired link">
          {rows.map((row) => (
            <li key={row.id}>
              <div className="who">
                <strong>{row.name}</strong>
                <span>{row.email}</span>
              </div>
              <div className="meta">
                <span className="badge">{row.role.replace(/_/g, " ")}</span>
                <span className="status error">Link expired</span>
                <button
                  id={`expired-resend-${row.id}`}
                  type="button"
                  className="btn small"
                  disabled={busyId === row.id}
                  aria-label={`Re-send set-password link to ${row.name}`}
                  onClick={() => void resend(row)}
                >
                  {busyId === row.id ? "Sending…" : "Re-send link"}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
