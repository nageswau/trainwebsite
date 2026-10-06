"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import TelecallerCampaignRow from "@/components/TelecallerCampaignRow";
import ProductOptions from "@/components/TelecallerProductOptions";
import { sendJson, type Page } from "@/lib/apiErrors";
import { formOptional, formText } from "@/lib/telecaller";
import { CAMPAIGNS_URL, CATALOGUE_PAGE_SIZE, SOURCES, SOURCE_LABEL, activeProducts, datesInOrder, getPage, type Campaign, type Product } from "@/lib/telecallerCatalogue";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

const FEEDBACK_ID = "camp-create-feedback";
type Feedback = { text: string; error: boolean };

// tel-002 (T16, P3/P4): the manager's campaign list -- "Instagram → Cyber Security → September 2026". A create form (one of the 13
// §2 sources, an active product, start required, end optional and not before the start) and the list with loading / error+Retry /
// empty / search / pager states. Managers see inactive campaigns too; the API decides who may write.
export default function TelecallerCampaignsPanel() {
  const [data, setData] = useState<Page<Campaign> | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [products, setProducts] = useState<Product[] | null>(null);
  const [productsFailed, setProductsFailed] = useState(false);
  const [offset, setOffset] = useState(0);
  const [query, setQuery] = useState("");
  const [draft, setDraft] = useState("");
  const [version, setVersion] = useState(0);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const inFlight = useRef(false); // `busy` disables the button only after a re-render; a double click must not POST twice
  const focus = useFocusAfterRender();

  useEffect(() => {
    const controller = new AbortController();
    setLoadFailed(false);
    const request = new URLSearchParams({ limit: String(CATALOGUE_PAGE_SIZE), offset: String(offset) });
    if (query) request.set("q", query);
    getPage<Campaign>(`${CAMPAIGNS_URL}?${request}`, controller.signal).then(setData).catch(() => controller.signal.aborted || setLoadFailed(true));
    return () => controller.abort();
  }, [offset, query, version]);

  const loadProducts = useCallback(() => {
    setProductsFailed(false);
    activeProducts().then(setProducts).catch(() => setProductsFailed(true));
  }, []);

  useEffect(() => {
    loadProducts();
  }, [loadProducts]);

  const reload = () => setVersion((v) => v + 1);
  const search = (text: string) => {
    setDraft(text);
    setQuery(text.trim());
    setOffset(0);
  };
  const noProducts = products !== null && products.length === 0;

  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    const formEl = event.currentTarget;
    const form = new FormData(formEl);
    const body = {
      name: formText(form, "name"), source: formText(form, "source"), product_id: formText(form, "product_id"),
      start_date: formText(form, "start_date"), end_date: formOptional(form, "end_date"),
    };
    if (!datesInOrder(body.start_date, body.end_date)) {
      setFeedback({ text: "End date cannot be before the start date", error: true });
      return focus(FEEDBACK_ID);
    }
    inFlight.current = true;
    setBusy(true);
    const outcome = await sendJson(CAMPAIGNS_URL, "POST", body);
    inFlight.current = false;
    setBusy(false);
    if (outcome.ok) {
      setFeedback({ text: `Created ${body.name}.`, error: false });
      formEl.reset();
      reload();
    } else {
      setFeedback({ text: outcome.message, error: true });
    }
    focus(FEEDBACK_ID);
  }

  return (
    <>
      <form className="action-card form" onSubmit={create} aria-describedby={FEEDBACK_ID}>
        <h3>Create campaign</h3>
        <div className="field"><label htmlFor="camp-name">Campaign name (required)</label><input id="camp-name" name="name" required maxLength={160} placeholder="e.g. Sep 2026 Cyber Security" disabled={busy} /></div>
        <div className="field">
          <label htmlFor="camp-source">Source (required)</label>
          <select id="camp-source" name="source" required defaultValue="" disabled={busy}>
            <option value="" disabled>Choose a source</option>
            {SOURCES.map((s) => <option key={s} value={s}>{SOURCE_LABEL[s]}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="camp-product">Product (required)</label>
          <select id="camp-product" name="product_id" required defaultValue="" disabled={busy || !products?.length}>
            <option value="" disabled>{products === null && !productsFailed ? "Loading products…" : "Choose a product"}</option>
            {products && <ProductOptions products={products} />}
          </select>
        </div>
        {productsFailed && (
          <p className="form-error" role="alert">
            Unable to load products. <button type="button" className="btn secondary small" onClick={loadProducts}>Retry loading products</button>
          </p>
        )}
        {noProducts && <p className="muted" style={{ fontSize: 13 }}>No active product — add or reactivate one on the <Link href="/telecaller/manager/products">Products</Link> page first.</p>}
        <div className="field"><label htmlFor="camp-start">Start date (required)</label><input id="camp-start" name="start_date" type="date" required disabled={busy} /></div>
        <div className="field"><label htmlFor="camp-end">End date</label><input id="camp-end" name="end_date" type="date" disabled={busy} /></div>
        <button className="btn" disabled={busy || !products?.length}>{busy ? "Creating…" : "Create campaign"}</button>
        <div id={FEEDBACK_ID} tabIndex={-1} className={feedback ? (feedback.error ? "form-error" : "form-message") : undefined} role="status" aria-live="polite" style={{ marginTop: 8, overflowWrap: "anywhere" }}>
          {feedback?.text}
        </div>
      </form>
      <div className="action-card wide telecaller-list" aria-busy={data === null && !loadFailed}>
        <h3>Campaigns</h3>
        <form role="search" onSubmit={(event) => { event.preventDefault(); search(draft); }} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
          <input type="search" aria-label="Search campaigns" placeholder="Campaign name" value={draft} maxLength={200} onChange={(event) => setDraft(event.target.value)} style={{ flex: "1 1 220px" }} />
          <button type="submit" className="btn secondary small">Search</button>
          {query && <button type="button" className="btn secondary small" onClick={() => search("")}>Clear search</button>}
        </form>
        <div className={notice ? "form-message" : undefined} role="status" aria-live="polite" style={notice ? { marginBottom: 8 } : undefined}>{notice}</div>
        {loadFailed ? (
          <>
            <p className="form-error" role="alert">Unable to load campaigns.</p>
            <button type="button" className="btn secondary small" onClick={reload}>Retry</button>
          </>
        ) : data === null ? (
          <p className="muted" role="status">Loading campaigns…</p>
        ) : data.items.length === 0 ? (
          <p className="empty" role="status">{query ? `No campaigns match “${query}”.` : "No campaigns yet. Use the Create campaign form to add the first one."}</p>
        ) : (
          <>
            <div className="table-wrap" role="region" aria-label="Campaigns" tabIndex={0}>
              <table>
                <thead>
                  <tr>
                    <th scope="col">Name</th><th scope="col">Source</th><th scope="col">Product</th><th scope="col">Dates</th>
                    <th scope="col">Status</th><th scope="col"><span className="visually-hidden">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((r) => <TelecallerCampaignRow key={r.id} row={r} products={products ?? []} onChanged={(text) => { setNotice(text); reload(); }} />)}
                </tbody>
              </table>
            </div>
            {data.total > CATALOGUE_PAGE_SIZE && (
              <nav aria-label="Campaign pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
                <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
                <button type="button" className="btn secondary small" aria-label="Previous page" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - CATALOGUE_PAGE_SIZE))}>Previous</button>
                <button type="button" className="btn secondary small" aria-label="Next page" disabled={data.offset + data.items.length >= data.total} onClick={() => setOffset(offset + CATALOGUE_PAGE_SIZE)}>Next</button>
              </nav>
            )}
          </>
        )}
      </div>
    </>
  );
}
