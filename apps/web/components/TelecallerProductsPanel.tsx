"use client";
import { useEffect, useRef, useState } from "react";

import CreateJumpLink from "@/components/CreateJumpLink";
import TelecallerProductRow from "@/components/TelecallerProductRow";
import { sendJson, type Page } from "@/lib/apiErrors";
import { formText } from "@/lib/telecaller";
import { CATALOGUE_PAGE_SIZE, GROUPS, GROUP_LABEL, PRODUCTS_URL, activePrograms, getPage, type Product, type ProductGroup, type ProgramOption } from "@/lib/telecallerCatalogue";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";
import { toneClass, type Feedback } from "@/lib/welcomeLink";

const FEEDBACK_ID = "prod-create-feedback";

// tel-002 (DEC-SCOPE-074): the manager's product/interest catalogue -- a create form (team only for Other, course only for IT; P2) and
// the list with loading / error+Retry / empty / pager states. Managers see inactive products too; the API decides who may write.
export default function TelecallerProductsPanel() {
  const [data, setData] = useState<Page<Product> | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [filter, setFilter] = useState<ProductGroup | "">("");
  const [offset, setOffset] = useState(0);
  const [version, setVersion] = useState(0);
  const [programs, setPrograms] = useState<ProgramOption[] | null>(null);
  const [group, setGroup] = useState<ProductGroup>("it");
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const inFlight = useRef(false); // `busy` disables the button only after a re-render; a double click must not POST twice
  const focus = useFocusAfterRender();

  useEffect(() => {
    const controller = new AbortController();
    setLoadFailed(false);
    const query = new URLSearchParams({ limit: String(CATALOGUE_PAGE_SIZE), offset: String(offset) });
    if (filter) query.set("group", filter);
    getPage<Product>(`${PRODUCTS_URL}?${query}`, controller.signal).then(setData).catch(() => controller.signal.aborted || setLoadFailed(true));
    return () => controller.abort();
  }, [filter, offset, version]);

  useEffect(() => {
    activePrograms().then(setPrograms).catch(() => setPrograms([]));
  }, []);

  const reload = () => setVersion((v) => v + 1);

  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    const formEl = event.currentTarget;
    const form = new FormData(formEl);
    const name = formText(form, "name");
    const body: Record<string, unknown> = { group, name };
    if (group === "other") body.team = formText(form, "team") || null;
    if (group === "it" && formText(form, "program_id")) body.program_id = formText(form, "program_id");
    setBusy(true);
    const outcome = await sendJson(PRODUCTS_URL, "POST", body);
    inFlight.current = false;
    setBusy(false);
    if (outcome.ok) {
      setFeedback({ text: `Created ${name}.`, tone: "success" });
      formEl.reset();
      setGroup("it");
      reload();
    } else {
      setFeedback({ text: outcome.message, tone: "error" });
    }
    focus(FEEDBACK_ID);
  }

  return (
    <>
      <form className="action-card form" onSubmit={create} aria-describedby={FEEDBACK_ID}>
        <h3>Create product</h3>
        <div className="field">
          <label htmlFor="prod-group">Group (required)</label>
          <select id="prod-group" name="group" value={group} onChange={(e) => setGroup(e.target.value as ProductGroup)} disabled={busy}>
            {GROUPS.map((g) => <option key={g} value={g}>{GROUP_LABEL[g]}</option>)}
          </select>
        </div>
        <div className="field"><label htmlFor="prod-name">Name (required)</label><input id="prod-name" name="name" required maxLength={120} disabled={busy} /></div>
        {group === "other" ? (
          <div className="field">
            <label htmlFor="prod-team">Team</label>
            <select id="prod-team" name="team" defaultValue="" disabled={busy}>
              <option value="">Unassigned queue</option><option value="it">IT</option><option value="overseas">Overseas</option>
            </select>
          </div>
        ) : (
          <p className="muted" style={{ fontSize: 13 }}>{group === "it" ? "IT products route to the IT team." : "Overseas products route to the Overseas team."}</p>
        )}
        {group === "it" && (
          programs === null ? <p className="muted" role="status">Loading courses…</p> : (
            <div className="field">
              <label htmlFor="prod-course">Linked IT course</label>
              <select id="prod-course" name="program_id" defaultValue="" disabled={busy}>
                <option value="">No linked course</option>
                {programs.map((p) => <option key={p.id} value={p.id}>{p.title}</option>)}
              </select>
            </div>
          )
        )}
        <button className="btn" disabled={busy}>{busy ? "Creating…" : "Create product"}</button>
        <div id={FEEDBACK_ID} tabIndex={-1} className={feedback ? toneClass[feedback.tone] : undefined} role="status" aria-live="polite" style={{ marginTop: 8, overflowWrap: "anywhere" }}>
          {feedback?.text}
        </div>
      </form>
      <div className="action-card wide telecaller-list" aria-busy={data === null && !loadFailed}>
        <h3>Products</h3>
        <CreateJumpLink targetId="prod-group" label="Create product" />
        <div className="field" style={{ maxWidth: 260 }}>
          <label htmlFor="prod-filter">Show</label>
          <select id="prod-filter" value={filter} onChange={(e) => { setFilter(e.target.value as ProductGroup | ""); setOffset(0); }}>
            <option value="">All groups</option>
            {GROUPS.map((g) => <option key={g} value={g}>{GROUP_LABEL[g]}</option>)}
          </select>
        </div>
        <div className={notice ? "form-message" : undefined} role="status" aria-live="polite" style={notice ? { marginBottom: 8 } : undefined}>{notice}</div>
        {loadFailed ? (
          <>
            <p className="form-error" role="alert">Unable to load products.</p>
            <button type="button" className="btn secondary small" onClick={reload}>Retry</button>
          </>
        ) : data === null ? (
          <p className="muted" role="status">Loading products…</p>
        ) : data.items.length === 0 ? (
          <p className="empty" role="status">{filter ? "No products in this group yet." : "No products yet."}</p>
        ) : (
          <>
            <div className="table-wrap" role="region" aria-label="Products" tabIndex={0}>
              <table>
                <thead>
                  <tr>
                    <th scope="col">Name</th><th scope="col">Group</th><th scope="col">Team</th><th scope="col">Course</th>
                    <th scope="col">Order</th><th scope="col">Status</th><th scope="col"><span className="visually-hidden">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((r) => <TelecallerProductRow key={r.id} row={r} programs={programs ?? []} onChanged={(text) => { setNotice(text); reload(); }} />)}
                </tbody>
              </table>
            </div>
            {data.total > CATALOGUE_PAGE_SIZE && (
              <nav aria-label="Product pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
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
