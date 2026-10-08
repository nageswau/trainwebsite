"use client";
import { useState } from "react";

import SearchableSelect from "@/components/SearchableSelect";
import { sendJson } from "@/lib/apiErrors";
import { placementManagerSearch, type RecruiterAdminRow } from "@/lib/recruiter";
import { USERS_URL, formOptional, formText, statusLabel } from "@/lib/telecaller";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// rec-001 (spec §5, AC5): one recruiter -- view, inline edit (Esc cancels), deactivate and reactivate. A recruiter from before the
// Recruiter Staff page has no Employee ID or manager; the row flags that and Edit sets both. The manager picker starts on the
// current manager, so an unrelated edit never silently reassigns the reporting line. The list refreshes only after the server says
// yes; focus returns to the row's controls on success and moves to the message on error. Reassigning open work is rec-037.
export default function AdminRecruiterRow({ row, onChanged }: { row: RecruiterAdminRow; onChanged: (notice: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const id = (name: string) => `rec-${name}-${row.id}`;
  const manager = row.reporting_manager;
  const currentManager = manager ? { id: manager.id, label: `${manager.full_name}${manager.active ? "" : " (inactive)"}` } : null;

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
      recruiter_profile: { employee_id: formText(form, "employee_id"), reporting_manager_user_id: formText(form, "manager") },
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
    if (!outcome.ok) return fail(outcome.message, id("status-error"));
    focus(id(active ? "deactivate" : "reactivate"), id("edit"));
    onChanged(`${active ? "Reactivated" : "Deactivated"} ${row.full_name}.`);
  }

  if (editing) {
    return (
      <tr>
        <td colSpan={5}>
          <form className="form" onSubmit={save} onKeyDown={(e) => { if (e.key === "Escape") close(); }} aria-describedby={id("error")}>
            <div className="field"><label htmlFor={id("name")}>Full name (required)</label><input id={id("name")} name="full_name" defaultValue={row.full_name} required maxLength={160} autoFocus disabled={busy} /></div>
            <div className="field"><label htmlFor={id("phone")}>Mobile</label><input id={id("phone")} name="phone" type="tel" inputMode="tel" defaultValue={row.phone ?? ""} maxLength={40} disabled={busy} /></div>
            <div className="field"><label htmlFor={id("emp")}>Employee ID (required)</label><input id={id("emp")} name="employee_id" defaultValue={row.employee_id ?? ""} required maxLength={40} disabled={busy} /></div>
            <SearchableSelect id={id("manager")} name="manager" label="Reporting manager (required)" noun="manager" required search={placementManagerSearch} initial={currentManager} disabled={busy} />
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
      <td data-label="Employee ID">{row.employee_id ?? <span className="muted">Not set</span>}</td>
      <td data-label="Manager">
        {manager ? <>{manager.full_name}{!manager.active && <> <span className="badge">No active manager</span></>}</> : <span className="badge">No manager</span>}
      </td>
      <td data-label="Status"><span className="badge">{statusLabel(row.active)}</span></td>
      <td data-label="Actions">
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <button id={id("edit")} type="button" className="btn secondary small" aria-label={`Edit ${row.full_name}`} onClick={() => { setError(null); setEditing(true); }} disabled={busy}>Edit</button>
          {row.active
            ? <button id={id("deactivate")} type="button" className="btn secondary small" aria-label={`Deactivate ${row.full_name}`} onClick={() => void setActive(false)} disabled={busy}>Deactivate</button>
            : <button id={id("reactivate")} type="button" className="btn secondary small" aria-label={`Reactivate ${row.full_name}`} onClick={() => void setActive(true)} disabled={busy}>Reactivate</button>}
        </div>
        {error && <p id={id("status-error")} tabIndex={-1} className="form-error" role="alert">{error}</p>}
      </td>
    </tr>
  );
}
