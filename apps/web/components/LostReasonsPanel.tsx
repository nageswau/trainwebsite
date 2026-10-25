"use client";
import { useEffect, useRef, useState } from "react";

import { sendJson, type Page } from "@/lib/apiErrors";
import { LOST_REASONS_URL, type LostReason } from "@/lib/leadStages";
import { formText, statusLabel } from "@/lib/telecaller";
import { getPage } from "@/lib/telecallerCatalogue";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";
import { toneClass, type Feedback } from "@/lib/welcomeLink";

const FEEDBACK_ID = "lost-reason-feedback";

// ccrm-006 (DEC-SCOPE-261, D8): the reasons a Lost / Not Interested close picks from -- create, rename / reorder, deactivate and
// reactivate (never delete: closed leads keep their reason). tel-002's products page layout; the API decides who may write.
export default function LostReasonsPanel() {
  const [data, setData] = useState<Page<LostReason> | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const inFlight = useRef(false); // a double click must not POST twice
  const focus = useFocusAfterRender();

  useEffect(() => {
    const controller = new AbortController();
    setLoadFailed(false);
    getPage<LostReason>(`${LOST_REASONS_URL}?limit=100`, controller.signal).then(setData).catch(() => controller.signal.aborted || setLoadFailed(true));
    return () => controller.abort();
  }, [version]);
  const reload = () => setVersion((v) => v + 1);

  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    const formEl = event.currentTarget;
    const name = formText(new FormData(formEl), "name");
    setBusy(true);
    const outcome = await sendJson(LOST_REASONS_URL, "POST", { name });
    inFlight.current = false;
    setBusy(false);
    if (outcome.ok) {
      setFeedback({ text: `Created ${name}.`, tone: "success" });
      formEl.reset();
      reload();
    } else {
      setFeedback({ text: outcome.message, tone: "error" });
    }
    focus(FEEDBACK_ID);
  }

  return (
    <>
      <form className="action-card form" onSubmit={create} aria-describedby={FEEDBACK_ID}>
        <h3>Create lost reason</h3>
        <div className="field"><label htmlFor="lost-reason-name">Name (required)</label><input id="lost-reason-name" name="name" required maxLength={120} disabled={busy} /></div>
        <button className="btn" disabled={busy}>{busy ? "Creating…" : "Create lost reason"}</button>
        <div id={FEEDBACK_ID} tabIndex={-1} className={feedback ? toneClass[feedback.tone] : undefined} role="status" aria-live="polite" style={{ marginTop: 8, overflowWrap: "anywhere" }}>
          {feedback?.text}
        </div>
      </form>
      <div className="action-card wide telecaller-list" aria-busy={data === null && !loadFailed}>
        <h3>Lost reasons</h3>
        <div className={notice ? "form-message" : undefined} role="status" aria-live="polite" style={notice ? { marginBottom: 8 } : undefined}>{notice}</div>
        {loadFailed ? (
          <>
            <p className="form-error" role="alert">Unable to load lost reasons.</p>
            <button type="button" className="btn secondary small" onClick={reload}>Retry</button>
          </>
        ) : data === null ? (
          <p className="muted" role="status">Loading lost reasons…</p>
        ) : data.items.length === 0 ? (
          <p className="empty" role="status">No lost reasons yet. Leads can&apos;t be closed as Lost or Not Interested until one exists.</p>
        ) : (
          <div className="table-wrap" role="region" aria-label="Lost reasons" tabIndex={0}>
            <table>
              <thead>
                <tr><th scope="col">Name</th><th scope="col">Order</th><th scope="col">Status</th><th scope="col"><span className="visually-hidden">Actions</span></th></tr>
              </thead>
              <tbody>
                {data.items.map((r) => <LostReasonRow key={r.id} row={r} onChanged={(text) => { setNotice(text); reload(); }} />)}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}

function LostReasonRow({ row, onChanged }: { row: LostReason; onChanged: (notice: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const id = (name: string) => `lost-reason-${name}-${row.id}`;

  async function patch(body: Record<string, unknown>, notice: string) {
    setError(null);
    setBusy(true);
    const outcome = await sendJson(`${LOST_REASONS_URL}/${row.id}`, "PATCH", body);
    setBusy(false);
    if (!outcome.ok) {
      setError(outcome.message);
      focus(id("error"));
      return;
    }
    setEditing(false);
    onChanged(notice);
  }

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const name = formText(form, "name");
    await patch({ name, sort_order: Number(formText(form, "sort_order")) }, `Saved ${name}.`);
  }

  if (editing) {
    return (
      <tr>
        <td colSpan={4}>
          <form className="form" onSubmit={save} onKeyDown={(e) => { if (e.key === "Escape") setEditing(false); }}>
            <div className="field"><label htmlFor={id("name")}>Reason name (required)</label><input id={id("name")} name="name" defaultValue={row.name} required maxLength={120} autoFocus disabled={busy} /></div>
            <div className="field"><label htmlFor={id("order")}>Order (required)</label><input id={id("order")} name="sort_order" type="number" inputMode="numeric" min={0} max={9999} step={1} defaultValue={row.sort_order} required disabled={busy} /></div>
            <div id={id("error")} tabIndex={-1} className={error ? "form-error" : undefined} role="alert">{error}</div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button className="btn small" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
              <button type="button" className="btn secondary small" onClick={() => setEditing(false)} disabled={busy}>Cancel</button>
            </div>
          </form>
        </td>
      </tr>
    );
  }
  return (
    <tr>
      <td data-label="Name">{row.name}</td>
      <td data-label="Order">{row.sort_order}</td>
      <td data-label="Status"><span className="badge">{statusLabel(row.active)}</span></td>
      <td data-label="Actions">
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <button type="button" className="btn secondary small" aria-label={`Edit ${row.name}`} onClick={() => { setError(null); setEditing(true); }} disabled={busy}>Edit</button>
          <button type="button" className="btn secondary small" aria-label={`${row.active ? "Deactivate" : "Reactivate"} ${row.name}`} disabled={busy}
            onClick={() => patch({ active: !row.active }, `${row.active ? "Deactivated" : "Reactivated"} ${row.name}.`)}>
            {row.active ? "Deactivate" : "Reactivate"}
          </button>
        </div>
        {error && <p id={id("error")} tabIndex={-1} className="form-error" role="alert">{error}</p>}
      </td>
    </tr>
  );
}
