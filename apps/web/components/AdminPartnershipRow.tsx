"use client";
import { useState } from "react";

import SearchableSelect from "@/components/SearchableSelect";
import { sendJson } from "@/lib/apiErrors";
import { headSearch, type PartnershipAdminRow } from "@/lib/partnership";
import { USERS_URL, formOptional, formText, statusLabel } from "@/lib/telecaller";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// upc-001 (spec §6): one partnership manager -- view, inline edit (Esc cancels), and deactivate (after an inline confirm) or
// reactivate through the plain PATCH (PU10; reassignment is upc-032). The list refreshes only after the server says yes. Focus returns
// to the row's controls on success and moves to the message on error. The head picker starts on the current head, so an unrelated
// edit never silently changes the reporting line.
export default function AdminPartnershipRow({ row, onChanged }: { row: PartnershipAdminRow; onChanged: (notice: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const id = (name: string) => `pm-${name}-${row.id}`;
  const currentHead = { id: row.reporting_head.id, label: `${row.reporting_head.full_name}${row.head_active ? "" : " (inactive)"}` };

  function close() {
    setEditing(false);
    setError(null);
    focus(id("edit"));
  }

  function fail(message: string, where: string) {
    setError(message);
    focus(where);
  }

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const fullName = formText(form, "full_name");
    setError(null);
    setBusy(true);
    const outcome = await sendJson(`${USERS_URL}/${row.id}`, "PATCH", {
      full_name: fullName, phone: formOptional(form, "phone"),
      partnership_profile: { employee_id: formText(form, "employee_id"), reporting_head_user_id: formText(form, "head") },
    });
    setBusy(false);
    if (!outcome.ok) return fail(outcome.message, id("error"));
    close();
    onChanged(`Saved ${fullName}.`);
  }

  async function setActive(active: boolean) {
    setError(null);
    setBusy(true);
    const outcome = await sendJson(`${USERS_URL}/${row.id}`, "PATCH", { active });
    setBusy(false);
    setConfirming(false);
    if (!outcome.ok) return fail(outcome.message, id("status-error"));
    focus(id(active ? "deactivate" : "reactivate"), id("edit"));
    onChanged(`${active ? "Reactivated" : "Deactivated"} ${row.full_name}.`);
  }

  function cancelConfirm() {
    setConfirming(false);
    focus(id("deactivate"));
  }

  if (editing) {
    return (
      <tr>
        <td colSpan={5}>
          <form className="form" onSubmit={save} onKeyDown={(e) => { if (e.key === "Escape") close(); }} aria-describedby={id("error")}>
            <div className="field"><label htmlFor={id("name")}>Full name (required)</label><input id={id("name")} name="full_name" defaultValue={row.full_name} required maxLength={160} autoFocus disabled={busy} /></div>
            <div className="field"><label htmlFor={id("phone")}>Mobile</label><input id={id("phone")} name="phone" type="tel" inputMode="tel" defaultValue={row.phone ?? ""} maxLength={40} disabled={busy} /></div>
            <div className="field"><label htmlFor={id("emp")}>Employee ID (required)</label><input id={id("emp")} name="employee_id" defaultValue={row.employee_id} required maxLength={40} disabled={busy} /></div>
            <SearchableSelect id={id("head")} name="head" label="Reporting head (required)" noun="head" required search={headSearch} initial={currentHead} disabled={busy} />
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
    // `data-label` names each cell's column, so below 640 px (globals.css .telecaller-list) a row becomes a card of labelled lines.
    <tr>
      <td data-label="Name">{row.full_name}<br /><span className="muted" style={{ fontSize: 12, overflowWrap: "anywhere" }}>{row.email}</span></td>
      <td data-label="Employee ID">{row.employee_id}</td>
      <td data-label="Head">{row.reporting_head.full_name}{!row.head_active && <> <span className="badge">No active head</span></>}</td>
      <td data-label="Status"><span className="badge">{statusLabel(row.active)}</span></td>
      <td data-label="Actions">
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <button id={id("edit")} type="button" className="btn secondary small" aria-label={`Edit ${row.full_name}`} onClick={() => { setError(null); setEditing(true); }} disabled={busy}>Edit</button>
          {row.active ? (
            confirming ? <>
              <button type="button" className="btn small" aria-label={`Confirm deactivate ${row.full_name}`} onClick={() => void setActive(false)} disabled={busy} autoFocus>{busy ? "Deactivating…" : "Confirm deactivate"}</button>
              <button type="button" className="btn secondary small" onClick={cancelConfirm} disabled={busy}>Keep active</button>
            </> : <button id={id("deactivate")} type="button" className="btn secondary small" aria-label={`Deactivate ${row.full_name}`} onClick={() => setConfirming(true)} disabled={busy}>Deactivate</button>
          ) : (
            <button id={id("reactivate")} type="button" className="btn secondary small" aria-label={`Reactivate ${row.full_name}`} onClick={() => void setActive(true)} disabled={busy}>Reactivate</button>
          )}
        </div>
        {error && <p id={id("status-error")} tabIndex={-1} className="form-error" role="alert">{error}</p>}
      </td>
    </tr>
  );
}
