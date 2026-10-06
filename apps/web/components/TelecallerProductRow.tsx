"use client";
import { useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { formText, statusLabel } from "@/lib/telecaller";
import { GROUP_LABEL, PRODUCTS_URL, teamLabel, type Product, type ProgramOption } from "@/lib/telecallerCatalogue";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// tel-002 (P2): one product -- view, inline edit (Esc cancels), deactivate with an inline confirm, reactivate. The group never changes;
// only an Other product's team and only an IT product's course link are editable. The list refreshes only after the server says yes.
export default function TelecallerProductRow({ row, programs, onChanged }: { row: Product; programs: ProgramOption[]; onChanged: (notice: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const id = (name: string) => `prod-${name}-${row.id}`;
  // The current link stays choosable even if that course has since been retired from the public list.
  const courses = row.program && !programs.some((p) => p.id === row.program!.id) ? [row.program, ...programs] : programs;

  function close() {
    setEditing(false);
    setError(null);
    focus(id("edit"));
  }

  async function patch(body: Record<string, unknown>, notice: string, errorAt: string) {
    setError(null);
    setBusy(true);
    const outcome = await sendJson(`${PRODUCTS_URL}/${row.id}`, "PATCH", body);
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
    const form = new FormData(event.currentTarget);
    const name = formText(form, "name");
    const body: Record<string, unknown> = { name, sort_order: Number(formText(form, "sort_order")) };
    if (row.group === "other") body.team = formText(form, "team") || null;
    if (row.group === "it") body.program_id = formText(form, "program_id") || null;
    if (await patch(body, `Saved ${name}.`, id("error"))) close();
  }

  async function setActive(active: boolean) {
    if (await patch({ active }, `${active ? "Reactivated" : "Deactivated"} ${row.name}.`, id("status-error"))) focus(active ? id("deactivate") : id("reactivate"), id("edit"));
  }

  if (editing) {
    return (
      <tr>
        <td colSpan={7}>
          <form className="form" onSubmit={save} onKeyDown={(e) => { if (e.key === "Escape") close(); }} aria-describedby={id("error")}>
            <div className="field"><span className="muted">Group</span> <strong>{GROUP_LABEL[row.group]} (cannot be changed)</strong></div>
            <div className="field"><label htmlFor={id("name")}>Product name (required)</label><input id={id("name")} name="name" defaultValue={row.name} required maxLength={120} autoFocus disabled={busy} /></div>
            {row.group === "other" && (
              <div className="field">
                <label htmlFor={id("team")}>Product team</label>
                <select id={id("team")} name="team" defaultValue={row.team ?? ""} disabled={busy}>
                  <option value="">Unassigned queue</option><option value="it">IT</option><option value="overseas">Overseas</option>
                </select>
              </div>
            )}
            {row.group === "it" && (
              <div className="field">
                <label htmlFor={id("course")}>Product course link</label>
                <select id={id("course")} name="program_id" defaultValue={row.program?.id ?? ""} disabled={busy}>
                  <option value="">No linked course</option>
                  {courses.map((p) => <option key={p.id} value={p.id}>{p.title}</option>)}
                </select>
              </div>
            )}
            <div className="field"><label htmlFor={id("order")}>Order (required)</label><input id={id("order")} name="sort_order" type="number" inputMode="numeric" min={0} max={9999} step={1} defaultValue={row.sort_order} required disabled={busy} /></div>
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
      <td data-label="Group">{GROUP_LABEL[row.group]}</td>
      <td data-label="Team">{teamLabel(row.team)}</td>
      <td data-label="Course">{row.program?.title ?? "—"}</td>
      <td data-label="Order">{row.sort_order}</td>
      <td data-label="Status"><span className="badge">{statusLabel(row.active)}</span></td>
      <td data-label="Actions">
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <button id={id("edit")} type="button" className="btn secondary small" aria-label={`Edit ${row.name}`} onClick={() => { setError(null); setEditing(true); }} disabled={busy}>Edit</button>
          {row.active && !confirming && <button id={id("deactivate")} type="button" className="btn secondary small" aria-label={`Deactivate ${row.name}`} onClick={() => { setError(null); setConfirming(true); focus(id("confirm")); }} disabled={busy}>Deactivate</button>}
          {!row.active && <button id={id("reactivate")} type="button" className="btn secondary small" aria-label={`Reactivate ${row.name}`} onClick={() => setActive(true)} disabled={busy}>Reactivate</button>}
        </div>
        {confirming && (
          <div role="group" aria-label={`Confirm deactivating ${row.name}`} style={{ marginTop: 6 }}>
            <p className="muted" style={{ fontSize: 13 }}>It disappears from pickers; leads and campaigns that already use it keep it.</p>
            <button id={id("confirm")} type="button" className="btn small" onClick={() => setActive(false)} disabled={busy}>Confirm deactivate</button>{" "}
            <button type="button" className="btn secondary small" onClick={() => { setConfirming(false); focus(id("deactivate")); }} disabled={busy}>Keep active</button>
          </div>
        )}
        {error && <p id={id("status-error")} tabIndex={-1} className="form-error" role="alert">{error}</p>}
      </td>
    </tr>
  );
}
