"use client";
import { useState } from "react";

import { LibraryEditFooter, LibraryRowActions, useLibraryRow } from "@/components/TelecallerLibraryRow";
import TelecallerScriptSteps, { draftStep, stepsBody, type StepDraft } from "@/components/TelecallerScriptSteps";
import { formText, statusLabel } from "@/lib/telecaller";
import type { Product } from "@/lib/telecallerCatalogue";
import { SCRIPTS_URL, type Script } from "@/lib/telecallerContent";

// tel-012 (C3): one script -- its ordered steps in the list; inline edit of name, product and steps; deactivate / reactivate (a
// reactivation onto a product that already has an active script is refused by the API, and its sentence is shown here).
export default function TelecallerScriptRow({ row, products, onChanged }: { row: Script; products: Product[]; onChanged: (notice: string) => void }) {
  const [steps, setSteps] = useState<StepDraft[]>([]);
  const state = useLibraryRow(SCRIPTS_URL, "script", row, onChanged, () => setSteps(row.steps.map((s) => draftStep(s))));
  const { editing, busy, id, patch, close } = state;
  // The current product stays choosable even if it has since been deactivated.
  const choices = products.some((p) => p.id === row.product.id) ? products : [row.product, ...products];

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const name = formText(form, "name");
    if (await patch({ name, product_id: formText(form, "product_id"), steps: stepsBody(steps) }, `Saved ${name}.`, id("error"))) close();
  }

  if (editing) {
    return (
      <tr>
        <td colSpan={5}>
          <form className="form" onSubmit={save} onKeyDown={(e) => { if (e.key === "Escape") close(); }} aria-describedby={id("error")}>
            <div className="field"><label htmlFor={id("name")}>Script name (required)</label><input id={id("name")} name="name" defaultValue={row.name} required maxLength={160} autoFocus disabled={busy} /></div>
            <div className="field">
              <label htmlFor={id("product")}>Script product (required)</label>
              <select id={id("product")} name="product_id" defaultValue={row.product.id} required disabled={busy}>
                {choices.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </div>
            <TelecallerScriptSteps idPrefix={id("steps")} steps={steps} onChange={setSteps} disabled={busy} />
            <LibraryEditFooter state={state} />
          </form>
        </td>
      </tr>
    );
  }

  return (
    <tr>
      <td data-label="Name">{row.name}</td>
      <td data-label="Product">{row.product.name}</td>
      <td data-label="Steps">
        <ol style={{ margin: 0, paddingLeft: 18 }}>
          {row.steps.map((s, i) => <li key={i}>{s.title}{s.notes ? <span className="muted"> — {s.notes}</span> : null}</li>)}
        </ol>
      </td>
      <td data-label="Status"><span className="badge">{statusLabel(row.active)}</span></td>
      <td data-label="Actions">
        <LibraryRowActions state={state} row={row} hint="Telecallers stop seeing it. Another script can then become this product's standard." />
      </td>
    </tr>
  );
}
