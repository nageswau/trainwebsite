"use client";
import { useRef, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { BDM_TYPE_LABEL, USERS_URL, formOptional, formText, statusLabel, type BdmAdminRow, type BdmManagerOption } from "@/lib/bdm";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// bdm-001 (spec §6.3): one BDM -- view, inline edit (type read-only, B7; Esc cancels, focus returns to Edit), and
// activate/deactivate with an inline confirm. The list refreshes only after the server says yes.
export default function AdminBdmRow({ row, managers, onChanged }: { row: BdmAdminRow; managers: BdmManagerOption[] | null; onChanged: (notice: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const editButton = useRef<HTMLButtonElement>(null);
  const focus = useFocusAfterRender();
  const id = (name: string) => `bdm-${name}-${row.id}`;
  // The current manager is ALWAYS an option -- whether inactive, missing from a failed/loading picker, or beyond its first page --
  // so the select keeps it and an unrelated edit can never silently reassign the reporting line (review Important #1).
  const current = { id: row.reporting_manager.id, full_name: `${row.reporting_manager.full_name}${row.manager_active ? "" : " (inactive)"}` };
  const options = [current, ...(managers ?? []).filter((m) => m.id !== current.id)];

  function close() {
    setEditing(false);
    setError(null);
    setTimeout(() => editButton.current?.focus(), 0);
  }

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    const outcome = await sendJson(`${USERS_URL}/${row.id}`, "PATCH", {
      full_name: formText(form, "full_name"), phone: formOptional(form, "phone"),
      bdm_profile: {
        employee_id: formText(form, "employee_id"), designation: formOptional(form, "designation"), department: formOptional(form, "department"),
        territory: formOptional(form, "territory"), reporting_manager_user_id: formText(form, "manager"),
      },
    });
    setBusy(false);
    if (!outcome.ok) return setError(outcome.message);
    close();
    onChanged(`Saved ${row.full_name}.`);
  }

  async function setActive(active: boolean) {
    setBusy(true);
    const outcome = await sendJson(`${USERS_URL}/${row.id}`, "PATCH", { active });
    setBusy(false);
    setConfirming(false);
    if (!outcome.ok) {
      setError(outcome.message);
      return focus(id("deactivate"), id("edit"));
    }
    onChanged(`${active ? "Reactivated" : "Deactivated"} ${row.full_name}.`);
  }

  function askToDeactivate() {
    setConfirming(true);
    focus(id("confirm"));
  }

  function keepActive() {
    setConfirming(false);
    focus(id("deactivate"));
  }

  if (editing) {
    return (
      <tr>
        <td colSpan={7}>
          <form className="form" onSubmit={save} onKeyDown={(e) => { if (e.key === "Escape") close(); }} aria-describedby={id("error")}>
            <div className="field"><label htmlFor={id("name")}>Full name (required)</label><input id={id("name")} name="full_name" defaultValue={row.full_name} required maxLength={160} autoFocus disabled={busy} /></div>
            <div className="field"><label htmlFor={id("phone")}>Mobile</label><input id={id("phone")} name="phone" type="tel" inputMode="tel" defaultValue={row.phone ?? ""} maxLength={40} disabled={busy} /></div>
            <div className="field"><span className="muted">Module</span> <strong>{BDM_TYPE_LABEL[row.bdm_type]} (cannot be changed)</strong></div>
            <div className="field"><label htmlFor={id("emp")}>Employee ID (required)</label><input id={id("emp")} name="employee_id" defaultValue={row.employee_id} required maxLength={40} disabled={busy} /></div>
            <div className="field"><label htmlFor={id("designation")}>Designation</label><input id={id("designation")} name="designation" defaultValue={row.designation ?? ""} maxLength={120} disabled={busy} /></div>
            <div className="field"><label htmlFor={id("department")}>Department</label><input id={id("department")} name="department" defaultValue={row.department ?? ""} maxLength={120} disabled={busy} /></div>
            <div className="field"><label htmlFor={id("territory")}>Territory</label><input id={id("territory")} name="territory" defaultValue={row.territory ?? ""} maxLength={120} disabled={busy} /></div>
            <div className="field">
              <label htmlFor={id("manager")}>Reporting manager (required)</label>
              <select id={id("manager")} name="manager" defaultValue={row.reporting_manager.id} required disabled={busy}>
                {options.map((m) => <option key={m.id} value={m.id}>{m.full_name}</option>)}
              </select>
            </div>
            <div id={id("error")} className={error ? "form-error" : undefined} role="alert">{error}</div>
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
      <td>{row.full_name}<br /><span className="muted" style={{ fontSize: 12, overflowWrap: "anywhere" }}>{row.email}</span></td>
      <td>{row.employee_id}</td>
      <td>{BDM_TYPE_LABEL[row.bdm_type]}</td>
      <td>{row.territory ?? "—"}</td>
      <td>{row.reporting_manager.full_name}{!row.manager_active && <> <span className="badge">No active manager</span></>}</td>
      <td><span className="badge">{statusLabel(row.active)}</span></td>
      <td>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <button ref={editButton} id={id("edit")} type="button" className="btn secondary small" aria-label={`Edit ${row.full_name}`} onClick={() => setEditing(true)} disabled={busy}>Edit</button>
          {row.active && !confirming && <button id={id("deactivate")} type="button" className="btn secondary small" aria-label={`Deactivate ${row.full_name}`} onClick={askToDeactivate} disabled={busy}>Deactivate</button>}
          {!row.active && <button type="button" className="btn secondary small" aria-label={`Reactivate ${row.full_name}`} onClick={() => setActive(true)} disabled={busy}>Reactivate</button>}
        </div>
        {confirming && (
          <div role="group" aria-label={`Confirm deactivating ${row.full_name}`} style={{ marginTop: 6 }}>
            <p className="muted" style={{ fontSize: 13 }}>Their reporting line and data stay; they can no longer sign in.</p>
            <button id={id("confirm")} type="button" className="btn small" onClick={() => setActive(false)} disabled={busy}>Confirm deactivate</button>{" "}
            <button type="button" className="btn secondary small" onClick={keepActive} disabled={busy}>Keep active</button>
          </div>
        )}
        {error && <p className="form-error" role="alert">{error}</p>}
      </td>
    </tr>
  );
}
