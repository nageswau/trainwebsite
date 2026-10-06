"use client";
import { useState } from "react";

import type { Product } from "@/lib/telecallerCatalogue";
import { BODY_LIMIT, CHANNEL_LABEL, KIND_LABEL, PLACEHOLDER_HINT, kindsFor, unknownPlaceholders, type Asset, type Channel, type Template } from "@/lib/telecallerContent";

type Props = {
  idPrefix: string;
  channel: Channel;
  onChannel?: (channel: Channel) => void; // create only: the channel is fixed once saved
  initial?: Template;
  products: Product[] | null;
  assets: Asset[] | null;
  disabled?: boolean;
};

// tel-012: the template fields shared by the create form and a row's edit form. Named inputs are read with FormData by the owner;
// the message is controlled so its length and unknown placeholders show as you type (the API decides -- AC3).
export default function TelecallerTemplateFields({ idPrefix, channel, onChannel, initial, products, assets, disabled }: Props) {
  const [body, setBody] = useState(initial?.body ?? "");
  const id = (name: string) => `${idPrefix}-${name}`;
  const unknown = unknownPlaceholders(body);
  // The current product / brochure stays choosable even if it has since been deactivated.
  const productChoices = initial?.product && !products?.some((p) => p.id === initial.product!.id) ? [initial.product, ...(products ?? [])] : (products ?? []);
  const assetChoices = initial?.asset && !assets?.some((a) => a.id === initial.asset!.id) ? [initial.asset, ...(assets ?? [])] : (assets ?? []);

  return (
    <>
      {onChannel ? (
        <div className="field">
          <label htmlFor={id("channel")}>Channel (required)</label>
          <select id={id("channel")} name="channel" value={channel} onChange={(e) => onChannel(e.target.value as Channel)} disabled={disabled}>
            <option value="whatsapp">WhatsApp</option><option value="email">Email</option>
          </select>
        </div>
      ) : (
        <div className="field"><span className="muted">Channel</span> <strong>{CHANNEL_LABEL[channel]} (cannot be changed)</strong></div>
      )}
      <div className="field">
        <label htmlFor={id("kind")}>Kind (required)</label>
        <select key={channel} id={id("kind")} name="kind" defaultValue={initial?.kind ?? kindsFor(channel)[0]} required disabled={disabled}>
          {kindsFor(channel).map((k) => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}
        </select>
      </div>
      <div className="field"><label htmlFor={id("name")}>Template name (required)</label><input id={id("name")} name="name" defaultValue={initial?.name} required maxLength={160} autoFocus={!!initial} disabled={disabled} /></div>
      <div className="field">
        <label htmlFor={id("product")}>Product</label>
        <select id={id("product")} name="product_id" defaultValue={initial?.product?.id ?? ""} disabled={disabled}>
          <option value="">Any product</option>
          {productChoices.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </div>
      <div className="field">
        <label htmlFor={id("asset")}>Brochure</label>
        <select id={id("asset")} name="asset_id" defaultValue={initial?.asset?.id ?? ""} disabled={disabled}>
          <option value="">No brochure</option>
          {assetChoices.map((a) => <option key={a.id} value={a.id}>{a.active ? a.name : `${a.name} (inactive)`}</option>)}
        </select>
      </div>
      {channel === "email" && (
        <div className="field"><label htmlFor={id("subject")}>Subject (required)</label><input id={id("subject")} name="subject" defaultValue={initial?.subject ?? ""} required maxLength={200} disabled={disabled} /></div>
      )}
      <div className="field">
        <label htmlFor={id("body")}>Message (required)</label>
        <textarea id={id("body")} name="body" value={body} onChange={(e) => setBody(e.target.value)} required rows={channel === "email" ? 8 : 4} maxLength={BODY_LIMIT[channel]} aria-describedby={`${id("hint")} ${id("count")}`} disabled={disabled} />
        <p id={id("hint")} className="muted" style={{ fontSize: 13 }}>{PLACEHOLDER_HINT}</p>
        <p id={id("count")} className="muted" style={{ fontSize: 13 }}>{body.length} / {BODY_LIMIT[channel]}</p>
        {unknown.length > 0 && <p className="form-warning" role="status">Unknown placeholder: {unknown.join(", ")}</p>}
      </div>
    </>
  );
}

/** The JSON both forms send: empty pickers become null; only email carries a subject. */
export function templateBody(form: FormData, channel: Channel): Record<string, unknown> {
  const text = (name: string) => String(form.get(name) ?? "").trim();
  const body: Record<string, unknown> = { kind: text("kind"), name: text("name"), product_id: text("product_id") || null, asset_id: text("asset_id") || null, body: String(form.get("body") ?? "") };
  if (channel === "email") body.subject = text("subject");
  return body;
}
