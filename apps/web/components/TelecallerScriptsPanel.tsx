"use client";
import { useEffect, useRef, useState } from "react";

import TelecallerContentList from "@/components/TelecallerContentList";
import TelecallerScriptRow from "@/components/TelecallerScriptRow";
import TelecallerScriptSteps, { draftStep, stepsBody, type StepDraft } from "@/components/TelecallerScriptSteps";
import { sendJson } from "@/lib/apiErrors";
import { formText } from "@/lib/telecaller";
import { activeProducts, type Product } from "@/lib/telecallerCatalogue";
import { SCRIPTS_URL, type Script } from "@/lib/telecallerContent";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";
import { useUrlList } from "@/lib/useUrlList";
import { toneClass, type Feedback } from "@/lib/welcomeLink";

const FEEDBACK_ID = "script-create-feedback";

// tel-012 (C3): the manager's call scripts -- one standard script per product, ordered steps. Create form + list filtered by product.
export default function TelecallerScriptsPanel() {
  const list = useUrlList<Script>(SCRIPTS_URL, "product_id");
  const [products, setProducts] = useState<Product[] | null>(null);
  const [steps, setSteps] = useState<StepDraft[]>(() => [draftStep()]);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const inFlight = useRef(false); // a double click must not POST twice
  const focus = useFocusAfterRender();

  useEffect(() => {
    activeProducts().then(setProducts).catch(() => setProducts([]));
  }, []);

  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    const formEl = event.currentTarget;
    const form = new FormData(formEl);
    const name = formText(form, "name");
    setBusy(true);
    const outcome = await sendJson(SCRIPTS_URL, "POST", { product_id: formText(form, "product_id"), name, steps: stepsBody(steps) });
    inFlight.current = false;
    setBusy(false);
    if (outcome.ok) {
      setFeedback({ text: `Created ${name}.`, tone: "success" });
      formEl.reset();
      setSteps([draftStep()]);
      list.reload();
    } else {
      setFeedback({ text: outcome.message, tone: "error" });
    }
    focus(FEEDBACK_ID);
  }

  return (
    <>
      <form className="action-card form" onSubmit={create} aria-describedby={FEEDBACK_ID}>
        <h3>Create script</h3>
        <p className="muted" style={{ fontSize: 13 }}>Each product has one active script: the standard steps every telecaller follows on a call.</p>
        <div className="field">
          <label htmlFor="script-product">Product (required)</label>
          <select id="script-product" name="product_id" required defaultValue="" disabled={busy || products === null}>
            <option value="" disabled>{products === null ? "Loading products…" : "Choose a product"}</option>
            {products?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
        <div className="field"><label htmlFor="script-name">Script name (required)</label><input id="script-name" name="name" required maxLength={160} disabled={busy} /></div>
        <TelecallerScriptSteps idPrefix="script-new" steps={steps} onChange={setSteps} disabled={busy} />
        <button className="btn" disabled={busy}>{busy ? "Creating…" : "Create script"}</button>
        <div id={FEEDBACK_ID} tabIndex={-1} className={feedback ? toneClass[feedback.tone] : undefined} role="status" aria-live="polite" style={{ marginTop: 8, overflowWrap: "anywhere" }}>
          {feedback?.text}
        </div>
      </form>
      <TelecallerContentList
        title="Scripts"
        noun="scripts"
        list={list}
        notice={notice}
        createTargetId="script-product"
        createLabel="Create script"
        headers={["Name", "Product", "Steps", "Status"]}
        filter={
          <div className="field" style={{ maxWidth: 260 }}>
            <label htmlFor="script-filter">Product</label>
            <select id="script-filter" value={list.filter} onChange={(e) => list.go(e.target.value, 0)}>
              <option value="">All products</option>
              {products?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
        }
      >
        {(items) => items.map((s) => <TelecallerScriptRow key={s.id} row={s} products={products ?? []} onChanged={(text) => { setNotice(text); list.reload(); }} />)}
      </TelecallerContentList>
    </>
  );
}
