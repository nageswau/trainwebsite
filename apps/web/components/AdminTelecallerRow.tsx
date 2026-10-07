"use client";
import { useState } from "react";

import AdminTelecallerLifecycle from "@/components/AdminTelecallerLifecycle";
import SearchableSelect from "@/components/SearchableSelect";
import { sendJson } from "@/lib/apiErrors";
import { TEAM_LABEL, USERS_URL, canMoveTeams, formOptional, formText, managerSearch, statusLabel, type TelecallerAdminRow } from "@/lib/telecaller";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

type Lifecycle = "deactivate" | "handover" | "move";

// tel-001 (spec §6.3): one telecaller -- view, inline edit (team read-only, TL7; Esc cancels) and reactivate. tel-025: Deactivate, Move
// team and (inactive rows) Reassign open work open AdminTelecallerLifecycle, which hands the open leads over. The list refreshes only
// after the server says yes. Focus returns to the row's controls on success and moves to the message on error. The manager picker
// starts on the current manager, so an unrelated edit never silently reassigns the reporting line.
export default function AdminTelecallerRow({ row, role, onChanged }: { row: TelecallerAdminRow; role: string; onChanged: (notice: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [lifecycle, setLifecycle] = useState<Lifecycle | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const id = (name: string) => `tel-${name}-${row.id}`;
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
    setError(null);
    setBusy(true);
    const outcome = await sendJson(`${USERS_URL}/${row.id}`, "PATCH", {
      full_name: fullName, phone: formOptional(form, "phone"),
      telecaller_profile: { employee_id: formText(form, "employee_id"), reporting_manager_user_id: formText(form, "manager") },
    });
    setBusy(false);
    if (!outcome.ok) return fail(outcome.message, id("error"));
    close();
    onChanged(`Saved ${fullName}.`); // QA-03: the name as saved, not as it was before the edit
  }

  async function reactivate() {
    setError(null);
    setBusy(true);
    const outcome = await sendJson(`${USERS_URL}/${row.id}`, "PATCH", { active: true });
    setBusy(false);
    if (!outcome.ok) return fail(outcome.message, id("status-error"));
    focus(id("deactivate"), id("edit"));
    onChanged(`Reactivated ${row.full_name}.`);
  }

  function start(kind: Lifecycle) {
    setError(null);
    setLifecycle(kind);
  }

  function endLifecycle() {
    const trigger = lifecycle;
    setLifecycle(null);
    if (trigger) focus(id(trigger));
  }

  if (editing) {
    return (
      <tr>
        <td colSpan={6}>
          <form className="form" onSubmit={save} onKeyDown={(e) => { if (e.key === "Escape") close(); }} aria-describedby={id("error")}>
            <div className="field"><label htmlFor={id("name")}>Full name (required)</label><input id={id("name")} name="full_name" defaultValue={row.full_name} required maxLength={160} autoFocus disabled={busy} /></div>
            <div className="field"><label htmlFor={id("phone")}>Mobile</label><input id={id("phone")} name="phone" type="tel" inputMode="tel" defaultValue={row.phone ?? ""} maxLength={40} disabled={busy} /></div>
            <div className="field"><span className="muted">Team</span> <strong>{TEAM_LABEL[row.team]} (cannot be changed here)</strong></div>
            <div className="field"><label htmlFor={id("emp")}>Employee ID (required)</label><input id={id("emp")} name="employee_id" defaultValue={row.employee_id} required maxLength={40} disabled={busy} /></div>
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
    // QA-04: `data-label` names each cell's column, so below 640 px (globals.css .telecaller-list) a row becomes a card of labelled lines.
    <tr>
      <td data-label="Name">{row.full_name}<br /><span className="muted" style={{ fontSize: 12, overflowWrap: "anywhere" }}>{row.email}</span></td>
      <td data-label="Employee ID">{row.employee_id}</td>
      <td data-label="Team">{TEAM_LABEL[row.team]}</td>
      <td data-label="Manager">{row.reporting_manager.full_name}{!row.manager_active && <> <span className="badge">No active manager</span></>}</td>
      <td data-label="Status"><span className="badge">{statusLabel(row.active)}</span></td>
      <td data-label="Actions">
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <button id={id("edit")} type="button" className="btn secondary small" aria-label={`Edit ${row.full_name}`} onClick={() => { setError(null); setEditing(true); }} disabled={busy}>Edit</button>
          {lifecycle === null && (row.active ? <>
            <button id={id("deactivate")} type="button" className="btn secondary small" aria-label={`Deactivate ${row.full_name}`} onClick={() => start("deactivate")} disabled={busy}>Deactivate</button>
            {canMoveTeams(role) && <button id={id("move")} type="button" className="btn secondary small" aria-label={`Move ${row.full_name} to another team`} onClick={() => start("move")} disabled={busy}>Move team</button>}
          </> : <>
            <button id={id("reactivate")} type="button" className="btn secondary small" aria-label={`Reactivate ${row.full_name}`} onClick={() => void reactivate()} disabled={busy}>Reactivate</button>
            <button id={id("handover")} type="button" className="btn secondary small" aria-label={`Reassign ${row.full_name}'s open leads`} onClick={() => start("handover")} disabled={busy}>Reassign open work</button>
          </>)}
        </div>
        {lifecycle && <AdminTelecallerLifecycle row={row} mode={lifecycle} onCancel={endLifecycle} onDone={(notice) => { setLifecycle(null); onChanged(notice); }} />}
        {error && <p id={id("status-error")} tabIndex={-1} className="form-error" role="alert">{error}</p>}
      </td>
    </tr>
  );
}
