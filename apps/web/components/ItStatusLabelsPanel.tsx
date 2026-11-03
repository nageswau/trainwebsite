"use client";
import { useEffect, useRef, useState } from "react";

import LocalTime from "@/components/LocalTime";
import { sendJson } from "@/lib/apiErrors";
import {
  ADMIN_STATUS_LABELS_URL, clearStatusLabels, statusLabelUrl, type AdminStatusEntry, type StatusCatalogue, type StatusKind,
} from "@/lib/statusLabels";
import { formText } from "@/lib/telecaller";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// itc-005 (DEC-SCOPE-362): the IT Admin renames, reorders and turns on/off the fixed IT lead and student statuses. The rules behind each
// state never change; a state the records decide can only be renamed and reordered. Turning off a state in use is allowed (Q-05): its
// rows keep it and still show its label, it is just not offered any more. The lost-reasons page layout; the API decides who may write.
const SECTIONS: { kind: StatusKind; title: string; inUse: string; hint: string }[] = [
  { kind: "lead", title: "Lead stages", inUse: "IT leads", hint: "Shown on every IT lead list, lead page, stage picker and filter." },
  { kind: "lifecycle", title: "Student lifecycle stages", inUse: "Set by hand", hint: "Shown on the student record and the student's own profile." },
];

export default function ItStatusLabelsPanel() {
  const [data, setData] = useState<StatusCatalogue<AdminStatusEntry> | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoadFailed(false);
    fetch(ADMIN_STATUS_LABELS_URL, { signal: controller.signal, cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error(String(response.status));
        setData(await response.json());
      })
      .catch(() => controller.signal.aborted || setLoadFailed(true));
    return () => controller.abort();
  }, [version]);

  if (loadFailed) {
    return (
      <div className="action-card wide">
        <p className="form-error" role="alert">Unable to load the status labels.</p>
        <button type="button" className="btn secondary small" onClick={() => setVersion((v) => v + 1)}>Retry</button>
      </div>
    );
  }
  if (data === null) return <div className="action-card wide" aria-busy="true"><p className="muted" role="status">Loading status labels…</p></div>;
  return (
    <>
      <div className={notice ? "form-message" : undefined} role="status" aria-live="polite">{notice}</div>
      {SECTIONS.map((section) => (
        <section key={section.kind} className="action-card wide telecaller-list" aria-labelledby={`status-${section.kind}`}>
          <h3 id={`status-${section.kind}`}>{section.title}</h3>
          <p className="muted" style={{ marginTop: 0 }}>{section.hint}</p>
          <div className="table-wrap" role="region" aria-label={`${section.title} table`} tabIndex={0}>
            <table>
              <thead>
                <tr>
                  <th scope="col">Label</th><th scope="col">Order</th><th scope="col">Status</th><th scope="col">{section.inUse}</th>
                  <th scope="col">Last changed</th><th scope="col"><span className="visually-hidden">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {data[section.kind].map((row) => (
                  <StatusRow key={row.code} kind={section.kind} row={row} onSaved={(text) => { clearStatusLabels(); setNotice(text); setVersion((v) => v + 1); }} />
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}
    </>
  );
}

function StatusRow({ kind, row, onSaved }: { kind: StatusKind; row: AdminStatusEntry; onSaved: (notice: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false); // a double click must not PUT twice
  const focus = useFocusAfterRender();
  const id = (name: string) => `status-${name}-${kind}-${row.code}`;
  // the toggle reloads the list; once this row comes back with its new state, put focus back on its button
  const toggleFocus = useRef(false);
  useEffect(() => {
    if (toggleFocus.current) document.getElementById(id("toggle"))?.focus();
    toggleFocus.current = false;
  }, [row.enabled]); // eslint-disable-line react-hooks/exhaustive-deps

  function close() {
    setEditing(false);
    setError(null);
    focus(id("edit"));
  }

  async function put(body: { label: string; sort_order: number; enabled: boolean }, notice: string) {
    if (inFlight.current) return;
    inFlight.current = true;
    setError(null);
    setBusy(true);
    const outcome = await sendJson(statusLabelUrl(kind, row.code), "PUT", body);
    inFlight.current = false;
    setBusy(false);
    if (!outcome.ok) {
      setError(outcome.message);
      focus(id("error"));
      return;
    }
    if (editing) setEditing(false);
    onSaved(notice);
  }

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const label = formText(form, "label");
    const order = formText(form, "sort_order");
    if (!label) return setError("Enter a label.");
    if (!/^\d{1,4}$/.test(order)) return setError("Enter an order from 0 to 9999.");
    await put({ label, sort_order: Number(order), enabled: row.enabled }, `Saved ${label}.`);
  }

  if (editing) {
    return (
      <tr>
        <td colSpan={6}>
          <form className="form" noValidate onSubmit={save} onKeyDown={(e) => { if (e.key === "Escape") close(); }}>
            <div className="field">
              <label htmlFor={id("label")}>Label (required)</label>
              <input id={id("label")} name="label" defaultValue={row.label} required maxLength={60} autoFocus disabled={busy} aria-describedby={id("default")} />
              <span id={id("default")} className="muted" style={{ fontSize: 13 }}>Default: {row.default_label}</span>
            </div>
            <div className="field">
              <label htmlFor={id("order")}>Order (required)</label>
              <input id={id("order")} name="sort_order" type="number" inputMode="numeric" min={0} max={9999} step={1} defaultValue={row.sort_order} required disabled={busy} />
            </div>
            <p id={id("error")} tabIndex={-1} className={error ? "form-error" : undefined} role="alert">{error}</p>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button className="btn small" disabled={busy}>{busy ? "Saving…" : `Save ${row.default_label} label`}</button>
              <button type="button" className="btn secondary small" onClick={close} disabled={busy}>Cancel</button>
            </div>
          </form>
        </td>
      </tr>
    );
  }
  const renamed = row.label !== row.default_label;
  return (
    <tr>
      <td data-label="Label">{row.label}{renamed && <div className="muted" style={{ fontSize: 13 }}>Default: {row.default_label}</div>}</td>
      <td data-label="Order">{row.sort_order}</td>
      <td data-label="Status"><span className="badge">{row.enabled ? "On" : "Off"}</span>{!row.can_disable && <div className="muted" style={{ fontSize: 13 }}>Set by the system</div>}</td>
      <td data-label={kind === "lead" ? "IT leads" : "Set by hand"}>{row.in_use}</td>
      <td data-label="Last changed">{row.updated_at ? <>{row.updated_by?.full_name ?? "—"} · <LocalTime value={row.updated_at} /></> : <span className="muted">Default</span>}</td>
      <td data-label="Actions">
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <button id={id("edit")} type="button" className="btn secondary small" aria-label={`Edit ${row.label}`} disabled={busy} onClick={() => { setError(null); setEditing(true); }}>Edit</button>
          {row.can_disable && (
            <button id={id("toggle")} type="button" className="btn secondary small" aria-label={`${row.enabled ? "Turn off" : "Turn on"} ${row.label}`} disabled={busy}
              onClick={() => { toggleFocus.current = true; void put({ label: row.label, sort_order: row.sort_order, enabled: !row.enabled }, `${row.enabled ? "Turned off" : "Turned on"} ${row.label}.${row.enabled && row.in_use ? ` ${row.in_use} existing ${row.in_use === 1 ? "record keeps" : "records keep"} it.` : ""}`); }}>
              {row.enabled ? "Turn off" : "Turn on"}
            </button>
          )}
        </div>
        {error && <p id={id("error")} tabIndex={-1} className="form-error" role="alert">{error}</p>}
      </td>
    </tr>
  );
}
