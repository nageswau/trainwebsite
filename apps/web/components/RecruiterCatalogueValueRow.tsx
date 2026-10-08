"use client";
import { useEffect, useRef, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import type { CatalogueValue } from "@/lib/recruiterCatalogue";
import { formText, statusLabel } from "@/lib/telecaller";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// rec-002: one value of a recruiter managed list -- view, inline rename (Esc cancels), deactivate with an inline confirm, reactivate.
// A rename keeps the id, so records keep their link; a deactivated value leaves the pickers but stays on records (the tel-002 row).
export default function RecruiterCatalogueValueRow({ row, url, noun, onChanged }: { row: CatalogueValue; url: string; noun: string; onChanged: (notice: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const id = (name: string) => `rec-value-${name}-${row.id}`;
  // After Deactivate/Reactivate the list reloads; once this row comes back with its new status, focus its new status button.
  const statusFocus = useRef<string | null>(null);
  useEffect(() => {
    const target = statusFocus.current ? document.getElementById(statusFocus.current) : null;
    statusFocus.current = null;
    target?.focus();
  }, [row.active]);

  function close() {
    setEditing(false);
    setError(null);
    focus(id("edit"));
  }

  async function patch(body: Record<string, unknown>, notice: string, errorAt: string) {
    setError(null);
    setBusy(true);
    const outcome = await sendJson(`${url}/${row.id}`, "PATCH", body);
    setBusy(false);
    setConfirming(false);
    if (!outcome.ok) {
      setError(outcome.message);
      focus(errorAt);
      return false;
    }
    onChanged(notice);
    return true;
  }

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = formText(new FormData(event.currentTarget), "name");
    if (await patch({ name }, `Saved ${name}.`, id("error"))) close();
  }

  async function setActive(active: boolean) {
    if (!(await patch({ active }, `${active ? "Reactivated" : "Deactivated"} ${row.name}.`, id("status-error")))) return;
    statusFocus.current = id(active ? "deactivate" : "reactivate");
    focus(id("edit"));
  }

  if (editing) {
    return (
      <tr>
        <td colSpan={3}>
          <form className="form" onSubmit={save} onKeyDown={(e) => { if (e.key === "Escape") close(); }} aria-describedby={id("error")}>
            <div className="field"><label htmlFor={id("name")}>{noun} name (required)</label><input id={id("name")} name="name" defaultValue={row.name} required maxLength={120} autoFocus disabled={busy} /></div>
            <div id={id("error")} tabIndex={-1} className={error ? "form-error" : undefined} role="alert">{error}</div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button className="btn small" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
              <button type="button" className="btn secondary small" onClick={close} disabled={busy}>Cancel</button>
            </div>
          </form>
        </td>
      </tr>
    );
  }

  return (
    <tr>
      <td data-label="Name">{row.name}</td>
      <td data-label="Status"><span className="badge">{statusLabel(row.active)}</span></td>
      <td data-label="Actions">
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <button id={id("edit")} type="button" className="btn secondary small" aria-label={`Edit ${row.name}`} onClick={() => { setError(null); setEditing(true); }} disabled={busy}>Edit</button>
          {row.active && !confirming && <button id={id("deactivate")} type="button" className="btn secondary small" aria-label={`Deactivate ${row.name}`} onClick={() => { setError(null); setConfirming(true); focus(id("confirm")); }} disabled={busy}>Deactivate</button>}
          {!row.active && <button id={id("reactivate")} type="button" className="btn secondary small" aria-label={`Reactivate ${row.name}`} onClick={() => setActive(true)} disabled={busy}>Reactivate</button>}
        </div>
        {confirming && (
          <div role="group" aria-label={`Confirm deactivating ${row.name}`} style={{ marginTop: 6 }}>
            <p className="muted" style={{ fontSize: 13 }}>It disappears from pickers; records that already use it keep it.</p>
            <button id={id("confirm")} type="button" className="btn small" onClick={() => setActive(false)} disabled={busy}>Confirm deactivate</button>{" "}
            <button type="button" className="btn secondary small" onClick={() => { setConfirming(false); focus(id("deactivate")); }} disabled={busy}>Keep active</button>
          </div>
        )}
        {error && <p id={id("status-error")} tabIndex={-1} className="form-error" role="alert">{error}</p>}
      </td>
    </tr>
  );
}
