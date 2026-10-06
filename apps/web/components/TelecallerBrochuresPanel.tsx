"use client";
import { useEffect, useRef, useState } from "react";

import TelecallerBrochureRow from "@/components/TelecallerBrochureRow";
import TelecallerContentList from "@/components/TelecallerContentList";
import { sendRequest } from "@/lib/apiErrors";
import { activeProducts, type Product } from "@/lib/telecallerCatalogue";
import { ASSETS_URL, ASSET_KIND_LABEL, type Asset, type AssetKind } from "@/lib/telecallerContent";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";
import { useUrlList } from "@/lib/useUrlList";
import { toneClass, type Feedback } from "@/lib/welcomeLink";

const FEEDBACK_ID = "asset-create-feedback";
const KINDS = Object.keys(ASSET_KIND_LABEL) as AssetKind[];
const isPdf = (file: File) => file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");

// tel-012 (C1): brochure and fee-sheet PDFs. Upload form + list filtered by kind; each row copies a signed link that opens without
// signing in for 7 days. The PDF check here only spares a pointless upload -- the API decides by the file's bytes.
export default function TelecallerBrochuresPanel() {
  const list = useUrlList<Asset>(ASSETS_URL, "kind", KINDS);
  const [products, setProducts] = useState<Product[] | null>(null);
  const [file, setFile] = useState<File | null>(null); // held here: the submit checks it before anything is sent
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const inFlight = useRef(false);
  const focus = useFocusAfterRender();

  useEffect(() => {
    activeProducts().then(setProducts).catch(() => setProducts([]));
  }, []);

  async function upload(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    const formEl = event.currentTarget;
    const form = new FormData(formEl);
    if (!file || !isPdf(file)) {
      setFeedback({ text: file ? "Upload a PDF file" : "Choose a PDF file", tone: "error" });
      return focus(FEEDBACK_ID);
    }
    form.set("file", file);
    inFlight.current = true;
    setBusy(true);
    const outcome = await sendRequest(ASSETS_URL, { method: "POST", body: form });
    inFlight.current = false;
    setBusy(false);
    if (outcome.ok) {
      setFeedback({ text: `Uploaded ${String(form.get("name")).trim()}.`, tone: "success" });
      formEl.reset();
      setFile(null);
      list.reload();
    } else {
      setFeedback({ text: outcome.message, tone: "error" });
    }
    focus(FEEDBACK_ID);
  }

  return (
    <>
      <form className="action-card form" onSubmit={upload} aria-describedby={FEEDBACK_ID}>
        <h3>Upload brochure</h3>
        <div className="field"><label htmlFor="asset-name">Brochure name (required)</label><input id="asset-name" name="name" required maxLength={160} disabled={busy} /></div>
        <div className="field">
          <label htmlFor="asset-kind">Kind (required)</label>
          <select id="asset-kind" name="kind" defaultValue="brochure" disabled={busy}>
            {KINDS.map((k) => <option key={k} value={k}>{ASSET_KIND_LABEL[k]}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="asset-product">Product</label>
          <select id="asset-product" name="product_id" defaultValue="" disabled={busy}>
            <option value="">Any product</option>
            {products?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="asset-file">PDF file (required)</label>
          <input id="asset-file" name="file" type="file" accept="application/pdf,.pdf" aria-required="true" aria-describedby="asset-file-hint" onChange={(e) => setFile(e.currentTarget.files?.[0] ?? null)} disabled={busy} />
          <p id="asset-file-hint" className="muted" style={{ fontSize: 13 }}>PDF only. Leads open it from a link that works for 7 days.</p>
        </div>
        <button className="btn" disabled={busy}>{busy ? "Uploading…" : "Upload brochure"}</button>
        <div id={FEEDBACK_ID} tabIndex={-1} className={feedback ? toneClass[feedback.tone] : undefined} role="status" aria-live="polite" style={{ marginTop: 8, overflowWrap: "anywhere" }}>
          {feedback?.text}
        </div>
      </form>
      <TelecallerContentList
        title="Brochures"
        noun="brochures"
        list={list}
        notice={notice}
        createTargetId="asset-name"
        createLabel="Upload brochure"
        headers={["Name", "Kind", "Product", "File", "Uploaded", "Status"]}
        filter={
          <div className="field" style={{ maxWidth: 260 }}>
            <label htmlFor="asset-filter">Show</label>
            <select id="asset-filter" value={list.filter} onChange={(e) => list.go(e.target.value, 0)}>
              <option value="">All kinds</option>
              {KINDS.map((k) => <option key={k} value={k}>{ASSET_KIND_LABEL[k]}</option>)}
            </select>
          </div>
        }
      >
        {(items) => items.map((a) => <TelecallerBrochureRow key={a.id} row={a} products={products ?? []} onChanged={(text) => { setNotice(text); list.reload(); }} onNotice={setNotice} />)}
      </TelecallerContentList>
    </>
  );
}
