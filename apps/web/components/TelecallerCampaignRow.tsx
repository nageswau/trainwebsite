"use client";
import { useState } from "react";

import ProductOptions from "@/components/TelecallerProductOptions";
import { sendJson } from "@/lib/apiErrors";
import { formOptional, formText, statusLabel } from "@/lib/telecaller";
import { CAMPAIGNS_URL, SOURCES, SOURCE_LABEL, campaignDates, datesInOrder, type Campaign, type Product } from "@/lib/telecallerCatalogue";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// tel-002 (P3/P4): one campaign -- view, inline edit (Esc cancels), deactivate with an inline confirm, reactivate. A campaign whose
// product was deactivated keeps it (offered as "(inactive)"); moving it needs an active product, which the API re-checks.
export default function TelecallerCampaignRow({ row, products, onChanged }: { row: Campaign; products: Product[]; onChanged: (notice: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const id = (name: string) => `camp-${name}-${row.id}`;
  const current = products.some((p) => p.id === row.product.id) ? null : row.product;

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
    const form = new FormData(event.currentTarget);
    const body = {
      name: formText(form, "name"), source: formText(form, "source"), product_id: formText(form, "product_id"),
      start_date: formText(form, "start_date"), end_date: formOptional(form, "end_date"),
    };
    if (!datesInOrder(body.start_date, body.end_date)) return fail("End date cannot be before the start date", id("error"));
    if (await patch(body, `Saved ${body.name}.`, id("error"))) close();
  }

  async function setActive(active: boolean) {
    if (await patch({ active }, `${active ? "Reactivated" : "Deactivated"} ${row.name}.`, id("status-error"))) focus(active ? id("deactivate") : id("reactivate"), id("edit"));
  }

  if (editing) {
    return (
      <tr>
        <td colSpan={6}>
          <form className="form" onSubmit={save} onKeyDown={(e) => { if (e.key === "Escape") close(); }} aria-describedby={id("error")}>
            <div className="field"><label htmlFor={id("name")}>Campaign name (required)</label><input id={id("name")} name="name" defaultValue={row.name} required maxLength={160} autoFocus disabled={busy} /></div>
            <div className="field">
              <label htmlFor={id("source")}>Campaign source (required)</label>
              <select id={id("source")} name="source" defaultValue={row.source} required disabled={busy}>
                {SOURCES.map((s) => <option key={s} value={s}>{SOURCE_LABEL[s]}</option>)}
              </select>
            </div>
            <div className="field">
              <label htmlFor={id("product")}>Campaign product (required)</label>
              <select id={id("product")} name="product_id" defaultValue={row.product.id} required disabled={busy}>
                {current && <option value={current.id}>{current.name} (inactive)</option>}
                <ProductOptions products={products} />
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
      <td data-label="Source">{SOURCE_LABEL[row.source] ?? row.source}</td>
      <td data-label="Product">{row.product.name}{!row.product.active && <> <span className="badge">Product inactive</span></>}</td>
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
            <p className="muted" style={{ fontSize: 13 }}>It disappears from pickers; leads that already use it keep it.</p>
            <button id={id("confirm")} type="button" className="btn small" onClick={() => setActive(false)} disabled={busy}>Confirm deactivate</button>{" "}
            <button type="button" className="btn secondary small" onClick={() => { setConfirming(false); focus(id("deactivate")); }} disabled={busy}>Keep active</button>
          </div>
        )}
        {error && <p id={id("status-error")} tabIndex={-1} className="form-error" role="alert">{error}</p>}
      </td>
    </tr>
  );
}
