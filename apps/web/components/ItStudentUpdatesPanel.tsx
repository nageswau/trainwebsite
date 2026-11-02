"use client";

import { useCallback, useEffect, useState } from "react";

import LocalTime from "@/components/LocalTime";
import { isPage } from "@/lib/apiErrors";
import { authorRole, MY_UPDATES_URL, PAGE_SIZE, type ItStudentUpdate } from "@/lib/itStudentNotes";

// itc-028 (DEC-SCOPE-351 N7): the IT student's Updates -- notes their counselor, trainer, HR or the IT Admin shared with them (GET
// /it/me/updates sends shared notes only, allow-listed fields). Newest share first; older ones load on request.
export default function ItStudentUpdatesPanel() {
  const [items, setItems] = useState<ItStudentUpdate[] | null>(null);
  const [total, setTotal] = useState(0);
  const [failed, setFailed] = useState(false);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async (offset: number) => {
    setLoading(true);
    setFailed(false);
    try {
      const response = await fetch(`${MY_UPDATES_URL}?limit=${PAGE_SIZE}&offset=${offset}`);
      const data: unknown = response.ok ? await response.json() : null;
      if (!isPage<ItStudentUpdate>(data)) throw new Error("not a page");
      setItems((current) => (offset === 0 || !current ? data.items : [...current, ...data.items.filter((u) => !current.some((c) => c.id === u.id))]));
      setTotal(data.total);
    } catch {
      setFailed(true);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    load(0);
  }, [load]);

  return (
    <section className="card" aria-labelledby="it-updates-heading" aria-busy={loading}>
      <h3 id="it-updates-heading">Shared with you</h3>
      {items === null && !failed && <p className="muted" role="status">Loading your updates…</p>}
      {items !== null && items.length === 0 && <p className="muted">No updates yet. When your counselor, trainer or HR team shares something with you, it appears here.</p>}
      {items !== null && items.length > 0 && (
        <ul style={{ paddingLeft: 0, listStyle: "none", margin: 0 }}>
          {items.map((u) => (
            <li key={u.id} style={{ padding: "10px 0", borderBottom: "1px solid var(--line, #e5e7eb)", overflowWrap: "anywhere" }}>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 12px", alignItems: "center", fontSize: 13 }}>
                <strong>{u.author_name}</strong>
                <span className="badge">{authorRole(u.author_role)}</span>
                <span className="muted"><LocalTime value={u.shared_at} time /></span>
              </div>
              <p style={{ margin: "6px 0 0", whiteSpace: "pre-wrap" }}>{u.body}</p>
            </li>
          ))}
        </ul>
      )}
      {failed && (
        <div role="alert">
          <p className="form-error">Your updates could not be loaded.</p>
          <button type="button" className="btn secondary small" onClick={() => load(items ? items.length : 0)}>Try again</button>
        </div>
      )}
      {items !== null && items.length < total && !failed && (
        <button type="button" className="btn secondary small" style={{ marginTop: 12 }} disabled={loading} onClick={() => load(items.length)}>
          {loading ? "Loading…" : "Load older updates"}
        </button>
      )}
    </section>
  );
}
