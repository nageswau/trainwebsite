"use client";

import { type FormEvent, useEffect, useState } from "react";

import { sendJson, sendRequest } from "@/lib/apiErrors";
import { isSavedSearch, SAVED_SEARCHES_URL, type SavedSearch, searchBody, type SearchState, stateOfBody } from "@/lib/recruiterCandidateSearch";

type Message = { text: string; error?: boolean } | null;
const FIELD = { marginBottom: 0 } as const;

/** hrc-020 (DEC-SCOPE-401 X1-X7): load one of my or the team's saved searches into the page (AC1, its filters through the URL), save the
 *  current search, and update or delete my own. The API decides who sees and changes what; this only hides what the row says is not mine. */
export default function RecruiterSavedSearches({ state, onLoad }: { state: SearchState; onLoad: (state: SearchState) => void }) {
  const [items, setItems] = useState<SavedSearch[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [selectedId, setSelectedId] = useState("");
  const [ignored, setIgnored] = useState<string[]>([]);
  const [message, setMessage] = useState<Message>(null);
  const [form, setForm] = useState<{ name: string; shared: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const body = searchBody(state);

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    fetch(SAVED_SEARCHES_URL, { signal: controller.signal })
      .then(async (response) => {
        const data = await response.json().catch(() => null);
        if (!response.ok || !Array.isArray(data?.items)) throw new Error(`Saved searches failed (${response.status})`);
        setItems((data.items as unknown[]).filter(isSavedSearch));
      })
      .catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [version]);

  const selected = items?.find((s) => s.id === selectedId) ?? null;
  const own = items?.filter((s) => s.mine) ?? [];
  const team = items?.filter((s) => !s.mine) ?? [];

  function load(id: string) {
    setSelectedId(id);
    setConfirming(false);
    setMessage(null);
    const search = items?.find((s) => s.id === id);
    setIgnored(search?.ignored ?? []);
    if (search) onLoad(stateOfBody(search.filters));
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!form || !body || busy) return;
    setBusy(true);
    const outcome = await sendJson(SAVED_SEARCHES_URL, "POST", { name: form.name, shared: form.shared, filters: body });
    setBusy(false);
    if (!outcome.ok || !isSavedSearch(outcome.data)) return setMessage({ text: outcome.ok ? "Unable to save this search." : outcome.message, error: true });
    const row = outcome.data;
    setItems((list) => [...(list ?? []), row]);
    setSelectedId(row.id);
    setIgnored([]);
    setForm(null);
    setMessage({ text: `Saved “${row.name}”.` });
  }

  async function update() {
    if (!selected || !body || busy) return;
    setBusy(true);
    const outcome = await sendJson(`${SAVED_SEARCHES_URL}/${encodeURIComponent(selected.id)}`, "PATCH", { filters: body });
    setBusy(false);
    if (!outcome.ok || !isSavedSearch(outcome.data)) return setMessage({ text: outcome.ok ? "Unable to update this search." : outcome.message, error: true });
    const row = outcome.data;
    setItems((list) => (list ?? []).map((s) => (s.id === row.id ? row : s)));
    setIgnored([]);
    setMessage({ text: `Updated “${row.name}” with the current filters.` });
  }

  async function remove() {
    if (!selected || busy) return;
    setBusy(true);
    const outcome = await sendRequest(`${SAVED_SEARCHES_URL}/${encodeURIComponent(selected.id)}`, { method: "DELETE" });
    setBusy(false);
    setConfirming(false);
    if (!outcome.ok) return setMessage({ text: outcome.message, error: true });
    setItems((list) => (list ?? []).filter((s) => s.id !== selected.id));
    setSelectedId("");
    setIgnored([]);
    setMessage({ text: `Deleted “${selected.name}”.` });
  }

  return (
    <section aria-labelledby="saved-searches-title" className="action-card" style={{ gap: 10 }}>
      <h2 id="saved-searches-title" style={{ fontSize: 18, margin: 0 }}>Saved searches</h2>
      {failed ? (
        <div className="actions" style={{ gap: 8, alignItems: "center" }}>
          <p className="form-error" role="status" style={{ margin: 0 }}>Unable to load saved searches.</p>
          <button type="button" className="btn secondary small" aria-label="Retry loading saved searches" onClick={() => setVersion((v) => v + 1)}>Retry</button>
        </div>
      ) : items === null ? (
        <p className="muted" role="status" style={{ margin: 0 }}>Loading saved searches…</p>
      ) : (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
          <div className="field" style={{ ...FIELD, flex: "1 1 16rem", minWidth: 0 }}>
            <label htmlFor="saved-search">Load a saved search</label>
            <select id="saved-search" value={selectedId} onChange={(e) => load(e.target.value)} disabled={busy}>
              <option value="">{items.length ? "Choose a saved search" : "No saved searches yet"}</option>
              {own.length > 0 && <optgroup label="My searches">{own.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</optgroup>}
              {team.length > 0 && (
                <optgroup label="Shared with the team">{team.map((s) => <option key={s.id} value={s.id}>{`${s.name} — ${s.owner.name}`}</option>)}</optgroup>
              )}
            </select>
          </div>
          {body && !form && (
            <button type="button" className="btn secondary small" onClick={() => { setForm({ name: "", shared: false }); setMessage(null); }}>Save this search</button>
          )}
          {selected?.can_edit && body && (
            <button type="button" className="btn secondary small" disabled={busy} onClick={update}>Update with current filters</button>
          )}
          {selected?.can_edit && !confirming && (
            <button type="button" className="btn ghost small" disabled={busy} onClick={() => setConfirming(true)}>Delete</button>
          )}
        </div>
      )}
      {confirming && selected && (
        <div className="actions" style={{ gap: 8, alignItems: "center" }}>
          <span>Delete “{selected.name}”{selected.shared ? " for the whole team" : ""}?</span>
          <button type="button" className="btn small" disabled={busy} onClick={remove}>Yes, delete</button>
          <button type="button" className="btn ghost small" onClick={() => setConfirming(false)}>Cancel</button>
        </div>
      )}
      {form && (
        <form onSubmit={save} aria-label="Save this search" style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
          <div className="field" style={{ ...FIELD, flex: "1 1 14rem", minWidth: 0 }}>
            <label htmlFor="saved-search-name">Saved search name</label>
            <input id="saved-search-name" required maxLength={80} autoFocus value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </div>
          <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <input type="checkbox" checked={form.shared} onChange={(e) => setForm({ ...form, shared: e.target.checked })} /> Share with the team
          </label>
          <button type="submit" className="btn small" disabled={busy || !form.name.trim()}>{busy ? "Saving…" : "Save"}</button>
          <button type="button" className="btn ghost small" onClick={() => setForm(null)}>Cancel</button>
        </form>
      )}
      {ignored.length > 0 && (
        <p className="muted" role="status" style={{ margin: 0 }}>
          Some filters in this saved search are no longer available and were ignored: {ignored.join(", ")}.
        </p>
      )}
      {message && (
        <p className={message.error ? "form-error" : "form-message"} role={message.error ? "alert" : "status"} style={{ margin: 0 }}>{message.text}</p>
      )}
    </section>
  );
}
