"use client";
import { useEffect, useRef, useState } from "react";

import TelecallerContentList from "@/components/TelecallerContentList";
import TelecallerTemplateFields, { templateBody } from "@/components/TelecallerTemplateFields";
import TelecallerTemplateRow from "@/components/TelecallerTemplateRow";
import { sendJson } from "@/lib/apiErrors";
import { activeProducts, type Product } from "@/lib/telecallerCatalogue";
import { TEMPLATES_URL, activeAssets, type Asset, type Channel, type Template } from "@/lib/telecallerContent";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";
import { useUrlList } from "@/lib/useUrlList";
import { toneClass, type Feedback } from "@/lib/welcomeLink";

const FEEDBACK_ID = "tpl-create-feedback";
const CHANNELS = ["whatsapp", "email"] as const;

// tel-012 (T9, C4): the manager's WhatsApp (§11) and email (§12) templates. Create form + list filtered by channel; each row previews
// with sample values (C2: rendering for a real lead arrives with tel-013/tel-014).
export default function TelecallerTemplatesPanel() {
  const list = useUrlList<Template>(TEMPLATES_URL, "channel", CHANNELS);
  const [products, setProducts] = useState<Product[] | null>(null);
  const [assets, setAssets] = useState<Asset[] | null>(null);
  const [channel, setChannel] = useState<Channel>("whatsapp");
  const [formKey, setFormKey] = useState(0); // remounts the fields (and their controlled message) after a create
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const inFlight = useRef(false);
  const focus = useFocusAfterRender();

  useEffect(() => {
    activeProducts().then(setProducts).catch(() => setProducts([]));
    activeAssets().then(setAssets).catch(() => setAssets([]));
  }, []);

  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    const fields = templateBody(new FormData(event.currentTarget), channel);
    setBusy(true);
    const outcome = await sendJson(TEMPLATES_URL, "POST", { channel, ...fields });
    inFlight.current = false;
    setBusy(false);
    if (outcome.ok) {
      setFeedback({ text: `Created ${fields.name}.`, tone: "success" });
      setFormKey((k) => k + 1);
      list.reload();
    } else {
      setFeedback({ text: outcome.message, tone: "error" });
    }
    focus(FEEDBACK_ID);
  }

  return (
    <>
      <form className="action-card form" onSubmit={create} aria-describedby={FEEDBACK_ID}>
        <h3>Create template</h3>
        <TelecallerTemplateFields key={formKey} idPrefix="tpl-new" channel={channel} onChannel={setChannel} products={products} assets={assets} disabled={busy} />
        <button className="btn" disabled={busy}>{busy ? "Creating…" : "Create template"}</button>
        <div id={FEEDBACK_ID} tabIndex={-1} className={feedback ? toneClass[feedback.tone] : undefined} role="status" aria-live="polite" style={{ marginTop: 8, overflowWrap: "anywhere" }}>
          {feedback?.text}
        </div>
      </form>
      <TelecallerContentList
        title="Templates"
        noun="templates"
        list={list}
        notice={notice}
        createTargetId="tpl-new-channel"
        createLabel="Create template"
        headers={["Name", "Channel", "Kind", "Product", "Brochure", "Status"]}
        filter={
          <div className="field" style={{ maxWidth: 260 }}>
            <label htmlFor="tpl-filter">Show</label>
            <select id="tpl-filter" value={list.filter} onChange={(e) => list.go(e.target.value, 0)}>
              <option value="">All channels</option><option value="whatsapp">WhatsApp</option><option value="email">Email</option>
            </select>
          </div>
        }
      >
        {(items) => items.map((t) => <TelecallerTemplateRow key={t.id} row={t} products={products} assets={assets} onChanged={(text) => { setNotice(text); list.reload(); }} />)}
      </TelecallerContentList>
    </>
  );
}
