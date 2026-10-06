"use client";
import { useState } from "react";

import { LibraryEditFooter, LibraryRowActions, useLibraryRow } from "@/components/TelecallerLibraryRow";
import TelecallerTemplateFields, { templateBody } from "@/components/TelecallerTemplateFields";
import { statusLabel } from "@/lib/telecaller";
import type { Product } from "@/lib/telecallerCatalogue";
import { CHANNEL_LABEL, KIND_LABEL, TEMPLATES_URL, type Asset, type Preview, type Template } from "@/lib/telecallerContent";
import { formatDate } from "@/lib/formatDate";

type PreviewState = { status: "loading" } | { status: "failed" } | { status: "ready"; preview: Preview };

// tel-012: one template -- inline edit (channel fixed), deactivate / reactivate, and a preview rendered by the API with sample values.
export default function TelecallerTemplateRow({ row, products, assets, onChanged }: { row: Template; products: Product[] | null; assets: Asset[] | null; onChanged: (notice: string) => void }) {
  const state = useLibraryRow(TEMPLATES_URL, "tpl", row, onChanged);
  const { editing, busy, id, patch, close } = state;
  const [preview, setPreview] = useState<PreviewState | null>(null);

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const body = templateBody(new FormData(event.currentTarget), row.channel);
    if (await patch(body, `Saved ${body.name}.`, id("error"))) {
      setPreview(null);
      close();
    }
  }

  async function togglePreview() {
    if (preview) return setPreview(null);
    setPreview({ status: "loading" });
    try {
      const response = await fetch(`${TEMPLATES_URL}/${row.id}/preview`);
      if (!response.ok) throw new Error(String(response.status));
      setPreview({ status: "ready", preview: await response.json() });
    } catch {
      setPreview({ status: "failed" });
    }
  }

  if (editing) {
    return (
      <tr>
        <td colSpan={7}>
          <form className="form" onSubmit={save} onKeyDown={(e) => { if (e.key === "Escape") close(); }} aria-describedby={id("error")}>
            <TelecallerTemplateFields idPrefix={id("f")} channel={row.channel} initial={row} products={products} assets={assets} disabled={busy} />
            <LibraryEditFooter state={state} />
          </form>
        </td>
      </tr>
    );
  }

  return (
    <>
      <tr>
        <td data-label="Name">{row.name}</td>
        <td data-label="Channel">{CHANNEL_LABEL[row.channel]}</td>
        <td data-label="Kind">{KIND_LABEL[row.kind] ?? row.kind}</td>
        <td data-label="Product">{row.product?.name ?? "Any"}</td>
        <td data-label="Brochure">{row.asset ? (row.asset.active ? row.asset.name : `${row.asset.name} (inactive)`) : "—"}</td>
        <td data-label="Status"><span className="badge">{statusLabel(row.active)}</span></td>
        <td data-label="Actions">
          <LibraryRowActions state={state} row={row} hint="It disappears from the telecallers' pickers; messages already sent keep its name.">
            <button type="button" className="btn secondary small" aria-label={`${preview ? "Hide preview of" : "Preview"} ${row.name}`} aria-expanded={!!preview} aria-controls={id("preview")} onClick={togglePreview} disabled={busy}>
              {preview ? "Hide preview" : "Preview"}
            </button>
          </LibraryRowActions>
        </td>
      </tr>
      {preview && (
        <tr id={id("preview")}>
          <td colSpan={7}>
            {preview.status === "loading" ? <p className="muted" role="status">Loading preview…</p>
              : preview.status === "failed" ? <p className="form-error" role="alert">Unable to load the preview.</p>
              : (
                <div role="region" aria-label={`Preview of ${row.name}`} style={{ display: "grid", gap: 6 }}>
                  <p className="muted" style={{ fontSize: 13 }}>Sample values: Priya Sharma, the template&apos;s product (or Cyber Security), Mon 14 Sept 2026, 10:30 AM.</p>
                  {preview.preview.subject !== null && <p><strong>Subject:</strong> {preview.preview.subject}</p>}
                  <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{preview.preview.body}</p>
                  {preview.preview.brochure_link && <p className="muted" style={{ fontSize: 13 }}>The brochure link works until {formatDate(preview.preview.brochure_link.expires_at, true)}.</p>}
                </div>
              )}
          </td>
        </tr>
      )}
    </>
  );
}
