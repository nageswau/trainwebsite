"use client";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import AdminBdmCreateForm from "@/components/AdminBdmCreateForm";
import AdminBdmRow from "@/components/AdminBdmRow";
import { isPage, type Page } from "@/lib/apiErrors";
import { BDMS_URL, MANAGERS_URL, PAGE_SIZE, type BdmAdminRow } from "@/lib/bdm";

// bdm-001 (spec §6.3): the admin's BDM list -- loading / error+Retry / empty / pager (AgentStaffPanel's pattern). The API scopes rows
// to the types this admin manages (D10); nothing here filters for security. The current page stays on screen while the next loads.
// Browser QA: the list card spans the full row (QA-01, `.action-card.wide`), it can be searched by name, email or Employee ID, and a
// newly created BDM is shown by filtering to its Employee ID (QA-04). The page and search live in the URL (?offset=&q=), so refresh
// keeps the place and Back returns to the previous page (QA-13); a page past the end offers a way back (QA-14).
function urlOffset(raw: string | null): number {
  const n = Number.parseInt(raw ?? "", 10);
  return Number.isFinite(n) && n > 0 ? n : 0;
}

export default function AdminBdmPanel({ role }: { role: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const fromUrl = { offset: urlOffset(params.get("offset")), query: (params.get("q") ?? "").trim() };
  const [data, setData] = useState<Page<BdmAdminRow> | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [offset, setOffset] = useState(fromUrl.offset);
  const [query, setQuery] = useState(fromUrl.query);
  const [draft, setDraft] = useState(fromUrl.query);

  // Back/Forward change the URL without remounting: follow it.
  useEffect(() => {
    setOffset(fromUrl.offset);
    setQuery(fromUrl.query);
    setDraft(fromUrl.query);
  }, [fromUrl.offset, fromUrl.query]);

  function go(nextOffset: number, nextQuery: string) {
    setOffset(nextOffset);
    setQuery(nextQuery);
    const next = new URLSearchParams();
    if (nextOffset > 0) next.set("offset", String(nextOffset));
    if (nextQuery) next.set("q", nextQuery);
    router.push(next.size ? `${pathname}?${next}` : pathname, { scroll: false });
  }
  const [version, setVersion] = useState(0);
  const [managersAvailable, setManagersAvailable] = useState<boolean | null>(null);
  const [managersFailed, setManagersFailed] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    setLoadFailed(false);
    const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
    if (query) params.set("q", query);
    fetch(`${BDMS_URL}?${params}`)
      .then(async (response) => {
        const body = await response.json().catch(() => null);
        if (!response.ok || !isPage<BdmAdminRow>(body)) throw new Error("not a page");
        setData(body);
      })
      .catch(() => setLoadFailed(true));
  }, [offset, query, version]);

  // Only "is there any active manager?" -- the picker itself searches the server (QA-02). A failed check is NOT "no managers"
  // (review Important #1): create stays disabled, with its own alert and Retry.
  const checkManagers = useCallback(() => {
    setManagersFailed(false);
    setManagersAvailable(null);
    fetch(`${MANAGERS_URL}?limit=1`)
      .then(async (response) => {
        const body = await response.json().catch(() => null);
        if (!response.ok || !isPage(body)) throw new Error("not a page");
        setManagersAvailable(body.total > 0);
      })
      .catch(() => setManagersFailed(true));
  }, []);

  useEffect(() => {
    checkManagers();
  }, [checkManagers]);

  const reload = () => setVersion((v) => v + 1);
  const search = (text: string) => {
    setDraft(text);
    go(0, text.trim());
  };

  return (
    <>
      {managersFailed && (
        <div className="action-card">
          <p className="form-error" role="alert">Unable to load BDM managers.</p>
          <button type="button" className="btn secondary small" onClick={checkManagers}>Retry loading managers</button>
        </div>
      )}
      <AdminBdmCreateForm role={role} managersAvailable={managersAvailable} onCreated={(employeeId) => { search(employeeId); reload(); }} />
      <div className="action-card wide bdm-list" aria-busy={data === null && !loadFailed}>
        <h3>BDMs</h3>
        <form role="search" onSubmit={(event) => { event.preventDefault(); search(draft); }} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
          <input type="search" aria-label="Search BDMs" placeholder="Name, email or Employee ID" value={draft} maxLength={200} onChange={(event) => setDraft(event.target.value)} style={{ flex: "1 1 220px" }} />
          <button type="submit" className="btn secondary small">Search</button>
          {query && <button type="button" className="btn secondary small" onClick={() => search("")}>Clear search</button>}
        </form>
        <div className={notice ? "form-message" : undefined} role="status" aria-live="polite" style={notice ? { marginBottom: 8 } : undefined}>{notice}</div>
        {loadFailed ? (
          <>
            <p className="form-error" role="alert">Unable to load BDMs.</p>
            <button type="button" className="btn secondary small" onClick={reload}>Retry</button>
          </>
        ) : data === null ? (
          <p className="muted" role="status">Loading BDMs…</p>
        ) : data.total === 0 ? (
          <p className="empty" role="status">{query ? `No BDMs match “${query}”.` : "No BDMs yet. Use the Create BDM form to add the first one."}</p>
        ) : data.items.length === 0 ? (
          <>
            <p className="empty" role="status">This page is past the end of the list.</p>
            <button type="button" className="btn secondary small" onClick={() => go(0, query)}>Go to the first page</button>
          </>
        ) : (
          <>
            <div className="table-wrap" role="region" aria-label="BDMs" tabIndex={0}>
              <table>
                <thead>
                  <tr>
                    <th scope="col">Name</th><th scope="col">Employee ID</th><th scope="col">Module</th><th scope="col">Territory</th>
                    <th scope="col">Manager</th><th scope="col">Status</th><th scope="col"><span className="visually-hidden">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((r) => (
                    <AdminBdmRow key={r.id} row={r} onChanged={(text) => { setNotice(text); reload(); }} />
                  ))}
                </tbody>
              </table>
            </div>
            {data.total > PAGE_SIZE && (
              <nav aria-label="BDM pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
                <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
                <button type="button" className="btn secondary small" aria-label="Previous page" disabled={data.offset === 0} onClick={() => go(Math.max(0, offset - PAGE_SIZE), query)}>Previous</button>
                <button type="button" className="btn secondary small" aria-label="Next page" disabled={data.offset + data.items.length >= data.total} onClick={() => go(offset + PAGE_SIZE, query)}>Next</button>
              </nav>
            )}
          </>
        )}
      </div>
    </>
  );
}
