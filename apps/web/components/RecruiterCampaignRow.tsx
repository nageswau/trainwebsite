"use client";
import { useEffect, useRef, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { CAMPAIGNS_URL, campaignBody, type CatalogueValue, type RecCampaign } from "@/lib/recruiterCatalogue";
import { statusLabel } from "@/lib/telecaller";
import { campaignDates, datesInOrder } from "@/lib/telecallerCatalogue";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// rec-002: one recruiter campaign -- view, inline edit (Esc cancels), deactivate with an inline confirm, reactivate. A campaign whose
// lead source was deactivated keeps it (offered as "(inactive)"); moving it needs an active source, which the API re-checks.
export default function RecruiterCampaignRow({ row, sources, onChanged }: { row: RecCampaign; sources: CatalogueValue[]; onChanged: (notice: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const id = (name: string) => `rec-camp-${name}-${row.id}`;
  const statusFocus = useRef<string | null>(null);
  useEffect(() => {
    const target = statusFocus.current ? document.getElementById(statusFocus.current) : null;
    statusFocus.current = null;
    target?.focus();
  }, [row.active]);
  const current = sources.some((s) => s.id === row.lead_source.id) ? null : row.lead_source;

  function close() {
    setEditing(false);
    setError(null);
    focus(id("edit"));
  }

  function fail(message: string, where: string) {
    setError(message);
    focus(where);
    return false;
  }

  async function patch(body: Record<string, unknown>, notice: string, errorAt: string) {
    setError(null);
    setBusy(true);
    const outcome = await sendJson(`${CAMPAIGNS_URL}/${row.id}`, "PATCH", body);
    setBusy(false);
    setConfirming(false);
    if (!outcome.ok) return fail(outcome.message, errorAt);
    onChanged(notice);
    return true;
  }

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const body = campaignBody(new FormData(event.currentTarget));
    if (!datesInOrder(body.start_date, body.end_date)) return fail("End date cannot be before the start date", id("error"));
    if (await patch(body, `Saved ${body.name}.`, id("error"))) close();
  }

  async function setActive(active: boolean) {
    if (!(await patch({ active }, `${active ? "Reactivated" : "Deactivated"} ${row.name}.`, id("status-error")))) return;
    statusFocus.current = id(active ? "deactivate" : "reactivate");
    focus(id("edit"));
  }

  if (editing) {
    return (
      <tr>
        <td colSpan={5}>
          <form className="form" onSubmit={save} onKeyDown={(e) => { if (e.key === "Escape") close(); }} aria-describedby={id("error")}>
            <div className="field"><label htmlFor={id("name")}>Campaign name (required)</label><input id={id("name")} name="name" defaultValue={row.name} required maxLength={160} autoFocus disabled={busy} /></div>
            <div className="field">
              <label htmlFor={id("source")}>Campaign lead source (required)</label>
              <select id={id("source")} name="lead_source_id" defaultValue={row.lead_source.id} required disabled={busy}>
                {current && <option value={current.id}>{current.name} (inactive)</option>}
                {sources.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
            <div className="field"><label htmlFor={id("start")}>Campaign start (required)</label><input id={id("start")} name="start_date" type="date" defaultValue={row.start_date} required disabled={busy} /></div>
            <div className="field"><label htmlFor={id("end")}>Campaign end</label><input id={id("end")} name="end_date" type="date" defaultValue={row.end_date ?? ""} disabled={busy} /></div>
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
      <td data-label="Lead source">{row.lead_source.name}{!row.lead_source.active && <> <span className="badge">Lead source inactive</span></>}</td>
      <td data-label="Dates">{campaignDates(row)}</td>
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
