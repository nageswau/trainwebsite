"use client";
import { useState } from "react";

import { LibraryEditFooter, LibraryRowActions, useLibraryRow } from "@/components/TelecallerLibraryRow";
import { formatDate } from "@/lib/formatDate";
import { formText, statusLabel } from "@/lib/telecaller";
import type { Product } from "@/lib/telecallerCatalogue";
import { ASSETS_URL, ASSET_KIND_LABEL, formatBytes, type Asset, type AssetLink } from "@/lib/telecallerContent";

type Props = { row: Asset; products: Product[]; onChanged: (notice: string) => void; onNotice: (notice: string) => void };

// tel-012 (C1): one brochure -- inline edit of its details (the file itself is fixed), deactivate (ends every link at once) /
// reactivate, and Copy link: a fresh signed link valid for 7 days, copied to the clipboard or shown to copy by hand.
export default function TelecallerBrochureRow({ row, products, onChanged, onNotice }: Props) {
  const state = useLibraryRow(ASSETS_URL, "asset", row, onChanged);
  const { editing, busy, setBusy, setError, id, patch, close, focus } = state;
  const [manualLink, setManualLink] = useState<string | null>(null);
  const choices = row.product && !products.some((p) => p.id === row.product!.id) ? [row.product, ...products] : products;

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const name = formText(form, "name");
    if (await patch({ name, kind: formText(form, "kind"), product_id: formText(form, "product_id") || null }, `Saved ${name}.`, id("error"))) close();
  }

  async function copyLink() {
    setError(null);
    setBusy(true);
    const response = await fetch(`${ASSETS_URL}/${row.id}/link`, { method: "POST" }).catch(() => null);
    setBusy(false);
    if (!response?.ok) {
      setError("Unable to create a link. Try again.");
      return focus(id("status-error"));
    }
    const link: AssetLink = await response.json();
    const until = formatDate(link.expires_at, true);
    try {
      await navigator.clipboard.writeText(link.url);
      setManualLink(null);
      onNotice(`Link copied for ${row.name}. It works until ${until}.`);
    } catch {
      setManualLink(link.url);
      onNotice(`Copy the link for ${row.name} below. It works until ${until}.`);
      focus(id("link"));
    }
  }

  if (editing) {
    return (
      <tr>
        <td colSpan={7}>
          <form className="form" onSubmit={save} onKeyDown={(e) => { if (e.key === "Escape") close(); }} aria-describedby={id("error")}>
            <div className="field"><label htmlFor={id("name")}>Brochure name (required)</label><input id={id("name")} name="name" defaultValue={row.name} required maxLength={160} autoFocus disabled={busy} /></div>
            <div className="field">
              <label htmlFor={id("kind")}>Brochure kind (required)</label>
              <select id={id("kind")} name="kind" defaultValue={row.kind} disabled={busy}>
                {Object.entries(ASSET_KIND_LABEL).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
              </select>
            </div>
            <div className="field">
              <label htmlFor={id("product")}>Brochure product</label>
              <select id={id("product")} name="product_id" defaultValue={row.product?.id ?? ""} disabled={busy}>
                <option value="">Any product</option>
                {choices.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </div>
            <p className="muted" style={{ fontSize: 13 }}>To change the file, upload a new brochure and deactivate this one.</p>
            <LibraryEditFooter state={state} />
          </form>
        </td>
      </tr>
    );
  }

  return (
    <tr>
      <td data-label="Name">{row.name}</td>
      <td data-label="Kind">{ASSET_KIND_LABEL[row.kind]}</td>
      <td data-label="Product">{row.product?.name ?? "Any"}</td>
      <td data-label="File" style={{ overflowWrap: "anywhere" }}>{row.file_name} <span className="muted">({formatBytes(row.size_bytes)})</span></td>
      <td data-label="Uploaded">{formatDate(row.uploaded_at)}</td>
      <td data-label="Status"><span className="badge">{statusLabel(row.active)}</span></td>
      <td data-label="Actions">
        <LibraryRowActions state={state} row={row} hint="Every link already sent stops working at once. Templates that use it stop offering a link.">
          {row.active && <button type="button" className="btn secondary small" aria-label={`Copy link for ${row.name}`} onClick={copyLink} disabled={busy}>Copy link</button>}
        </LibraryRowActions>
        {manualLink && row.active && (
          <div className="field" style={{ marginTop: 6 }}>
            <label htmlFor={id("link")}>Link for {row.name}</label>
            <input id={id("link")} readOnly value={manualLink} onFocus={(e) => e.currentTarget.select()} />
          </div>
        )}
      </td>
    </tr>
  );
}
