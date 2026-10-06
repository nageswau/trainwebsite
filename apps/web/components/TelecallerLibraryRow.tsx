"use client";
import { useEffect, useRef, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

type Row = { id: string; name: string; active: boolean };

// tel-012: the lifecycle every library row shares (the TelecallerProductRow behaviour): inline edit (Esc cancels), deactivate with an
// inline confirm, reactivate; the list refreshes only after the server says yes, and focus lands on the row's new status button.
export function useLibraryRow(url: string, prefix: string, row: Row, onChanged: (notice: string) => void, onEdit?: () => void) {
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const id = (name: string) => `${prefix}-${name}-${row.id}`;
  const statusFocus = useRef<string | null>(null);
  useEffect(() => {
    const target = statusFocus.current ? document.getElementById(statusFocus.current) : null;
    statusFocus.current = null;
    target?.focus();
  }, [row.active]);

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

  function startEdit() {
    setError(null);
    onEdit?.();
    setEditing(true);
  }

  function close() {
    setEditing(false);
    setError(null);
    focus(id("edit"));
  }

  async function setActive(active: boolean) {
    if (!(await patch({ active }, `${active ? "Reactivated" : "Deactivated"} ${row.name}.`, id("status-error")))) return;
    statusFocus.current = id(active ? "deactivate" : "reactivate");
    focus(id("edit"));
  }

  return { editing, startEdit, confirming, setConfirming, busy, setBusy, error, setError, focus, id, patch, close, setActive };
}

export type LibraryRow = ReturnType<typeof useLibraryRow>;

/** Edit / Deactivate (with confirm) / Reactivate, plus any row-specific buttons in `children`. */
export function LibraryRowActions({ state, row, hint, children }: { state: LibraryRow; row: Row; hint: string; children?: React.ReactNode }) {
  const { busy, confirming, setConfirming, setError, startEdit, focus, id, setActive, error, editing } = state;
  return (
    <>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        <button id={id("edit")} type="button" className="btn secondary small" aria-label={`Edit ${row.name}`} onClick={startEdit} disabled={busy}>Edit</button>
        {children}
        {row.active && !confirming && <button id={id("deactivate")} type="button" className="btn secondary small" aria-label={`Deactivate ${row.name}`} onClick={() => { setError(null); setConfirming(true); focus(id("confirm")); }} disabled={busy}>Deactivate</button>}
        {!row.active && <button id={id("reactivate")} type="button" className="btn secondary small" aria-label={`Reactivate ${row.name}`} onClick={() => setActive(true)} disabled={busy}>Reactivate</button>}
      </div>
      {confirming && (
        <div role="group" aria-label={`Confirm deactivating ${row.name}`} style={{ marginTop: 6 }}>
          <p className="muted" style={{ fontSize: 13 }}>{hint}</p>
          <button id={id("confirm")} type="button" className="btn small" onClick={() => setActive(false)} disabled={busy}>Confirm deactivate</button>{" "}
          <button type="button" className="btn secondary small" onClick={() => { setConfirming(false); focus(id("deactivate")); }} disabled={busy}>Keep active</button>
        </div>
      )}
      {error && !editing && <p id={id("status-error")} tabIndex={-1} className="form-error" role="alert">{error}</p>}
    </>
  );
}

/** The edit form's error line and Save / Cancel buttons. */
export function LibraryEditFooter({ state }: { state: LibraryRow }) {
  const { id, error, busy, close } = state;
  return (
    <>
      <div id={id("error")} tabIndex={-1} className={error ? "form-error" : undefined} role="alert">{error}</div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button className="btn small" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
        <button type="button" className="btn secondary small" onClick={close} disabled={busy}>Cancel</button>
      </div>
    </>
  );
}
