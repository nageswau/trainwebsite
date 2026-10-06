"use client";
import { useState } from "react";

import AdminBdmHandover from "@/components/AdminBdmHandover";
import SearchableSelect from "@/components/SearchableSelect";
import { sendJson } from "@/lib/apiErrors";
import { BDM_TYPE_LABEL, USERS_URL, formOptional, formText, managerSearch, statusLabel, type BdmAdminRow } from "@/lib/bdm";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// bdm-001 (spec §6.3): one BDM -- view, inline edit (type read-only, B7; Esc cancels), and activate/deactivate with an inline
// confirm. The list refreshes only after the server says yes. Focus is never dropped to <body> (QA-06): success returns it to the
// row's own controls, an error moves it to the message. The manager picker searches the server (QA-02) and starts on the current
// manager -- inactive or not -- so an unrelated edit can never silently reassign the reporting line.
// bdm-025: Deactivate opens AdminBdmHandover (who takes over the open work); an inactive row offers Hand over for work kept with them.
// Only reactivation still goes through PATCH -- it restores sign-in, never the old portfolio.
export default function AdminBdmRow({ row, onChanged }: { row: BdmAdminRow; onChanged: (notice: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [handover, setHandover] = useState<"deactivate" | "handover" | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const id = (name: string) => `bdm-${name}-${row.id}`;
  const currentManager = { id: row.reporting_manager.id, label: `${row.reporting_manager.full_name}${row.manager_active ? "" : " (inactive)"}` };

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
    setBusy(true);
    const outcome = await sendJson(`${USERS_URL}/${row.id}`, "PATCH", {
      full_name: fullName, phone: formOptional(form, "phone"),
      bdm_profile: {
        employee_id: formText(form, "employee_id"), designation: formOptional(form, "designation"), department: formOptional(form, "department"),
        territory: formOptional(form, "territory"), reporting_manager_user_id: formText(form, "manager"),
      },
    });
    setBusy(false);
    if (!outcome.ok) return fail(outcome.message, id("error"));
    close();
    onChanged(`Saved ${fullName}.`); // tel-001 QA follow-up: the name as saved, not as it was before the edit
  }

  async function reactivate() {
    setBusy(true);
    const outcome = await sendJson(`${USERS_URL}/${row.id}`, "PATCH", { active: true });
    setBusy(false);
    if (!outcome.ok) return fail(outcome.message, id("status-error"));
    // The opposite action appears once the list reloads; until then the row's Edit button holds focus.
    focus(id("deactivate"), id("edit"));
    onChanged(`Reactivated ${row.full_name}.`);
  }

  function closeHandover() {
    focus(handover === "deactivate" ? id("deactivate") : id("handover"));
    setHandover(null);
  }

  function handedOver(notice: string) {
    // After a deactivation the row reloads as inactive (Reactivate appears); until then Edit holds focus.
    focus(handover === "deactivate" ? id("reactivate") : id("handover"), id("edit"));
    setHandover(null);
    onChanged(notice);
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
            <SearchableSelect id={id("manager")} name="manager" label="Reporting manager (required)" noun="manager" required search={managerSearch} initial={currentManager} disabled={busy} />
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
    // tel-001 QA follow-up: `data-label` names each cell's column, so below 640 px (globals.css .bdm-list) a row becomes a card.
    <tr>
      <td data-label="Name">{row.full_name}<br /><span className="muted" style={{ fontSize: 12, overflowWrap: "anywhere" }}>{row.email}</span></td>
      <td data-label="Employee ID">{row.employee_id}</td>
      <td data-label="Module">{BDM_TYPE_LABEL[row.bdm_type]}</td>
      <td data-label="Territory">{row.territory ?? "—"}</td>
      <td data-label="Manager">{row.reporting_manager.full_name}{!row.manager_active && <> <span className="badge">No active manager</span></>}</td>
      <td data-label="Status"><span className="badge">{statusLabel(row.active)}</span></td>
      <td data-label="Actions">
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <button id={id("edit")} type="button" className="btn secondary small" aria-label={`Edit ${row.full_name}`} onClick={() => setEditing(true)} disabled={busy}>Edit</button>
          {row.active && !handover && <button id={id("deactivate")} type="button" className="btn secondary small" aria-label={`Deactivate ${row.full_name}`} onClick={() => setHandover("deactivate")} disabled={busy}>Deactivate</button>}
          {!row.active && <button id={id("reactivate")} type="button" className="btn secondary small" aria-label={`Reactivate ${row.full_name}`} onClick={() => void reactivate()} disabled={busy}>Reactivate</button>}
          {!row.active && !handover && <button id={id("handover")} type="button" className="btn secondary small" aria-label={`Hand over ${row.full_name}'s open work`} onClick={() => setHandover("handover")} disabled={busy}>Hand over</button>}
        </div>
        {handover && <AdminBdmHandover row={row} mode={handover} onDone={handedOver} onCancel={closeHandover} />}
        {error && <p id={id("status-error")} tabIndex={-1} className="form-error" role="alert">{error}</p>}
      </td>
    </tr>
  );
}
