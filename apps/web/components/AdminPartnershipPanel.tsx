"use client";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import AdminPartnershipCreateForm from "@/components/AdminPartnershipCreateForm";
import AdminPartnershipRow from "@/components/AdminPartnershipRow";
import CreateJumpLink from "@/components/CreateJumpLink";
import { isPage, type Page } from "@/lib/apiErrors";
import { HEADS_URL, MANAGERS_URL, type PartnershipAdminRow } from "@/lib/partnership";
import { PAGE_SIZE, pageOffset } from "@/lib/telecaller";

// upc-001 (spec §6): the admin's partnership manager list -- loading / error+Retry / empty / pager, the AdminTelecallerPanel pattern.
// The API decides who may read it (super_admin, overseas_admin); nothing here filters for security. Page and search live in the URL
// (?offset=&q=), so refresh keeps the place and Back returns to the previous page; a new manager is shown by filtering to its Employee ID.
async function fetchPage<T>(url: string): Promise<Page<T>> {
  const response = await fetch(url);
  const body = await response.json().catch(() => null);
  if (!response.ok || !isPage<T>(body)) throw new Error("not a page");
  return body;
}

export default function AdminPartnershipPanel() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const fromUrl = { offset: pageOffset(params.get("offset") ?? undefined), query: (params.get("q") ?? "").trim() };
  const [data, setData] = useState<Page<PartnershipAdminRow> | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [offset, setOffset] = useState(fromUrl.offset);
  const [query, setQuery] = useState(fromUrl.query);
  const [draft, setDraft] = useState(fromUrl.query);
  const [version, setVersion] = useState(0);
  const [headsAvailable, setHeadsAvailable] = useState<boolean | null>(null);
  const [headsFailed, setHeadsFailed] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

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

  useEffect(() => {
    setLoadFailed(false);
    const request = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
    if (query) request.set("q", query);
    fetchPage<PartnershipAdminRow>(`${MANAGERS_URL}?${request}`).then(setData).catch(() => setLoadFailed(true));
  }, [offset, query, version]);

  // Only "is there any active head?" -- the picker itself searches the server. A failed check is not "no heads".
  const checkHeads = useCallback(() => {
    setHeadsFailed(false);
    setHeadsAvailable(null);
    fetchPage(`${HEADS_URL}?limit=1`)
      .then((page) => setHeadsAvailable(page.total > 0))
      .catch(() => setHeadsFailed(true));
  }, []);

  useEffect(() => {
    checkHeads();
  }, [checkHeads]);

  const reload = () => setVersion((v) => v + 1);
  const search = (text: string) => {
    setDraft(text);
    go(0, text.trim());
  };

  return (
    <>
      {headsFailed && (
        <div className="action-card">
          <p className="form-error" role="alert">Unable to load partnership heads.</p>
          <button type="button" className="btn secondary small" onClick={checkHeads}>Retry loading heads</button>
        </div>
      )}
      <AdminPartnershipCreateForm headsAvailable={headsAvailable} onCreated={(employeeId) => { search(employeeId); reload(); }} />
      <div className="action-card wide telecaller-list" aria-busy={data === null && !loadFailed}>
        <h3>Partnership managers</h3>
        <CreateJumpLink targetId="pm-name" label="Create partnership manager" />
        <form role="search" onSubmit={(event) => { event.preventDefault(); search(draft); }} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
          <input type="search" aria-label="Search partnership managers" placeholder="Name, email or Employee ID" value={draft} maxLength={200} onChange={(event) => setDraft(event.target.value)} style={{ flex: "1 1 220px" }} />
          <button type="submit" className="btn secondary small">Search</button>
          {query && <button type="button" className="btn secondary small" onClick={() => search("")}>Clear search</button>}
        </form>
        <div className={notice ? "form-message" : undefined} role="status" aria-live="polite" style={notice ? { marginBottom: 8 } : undefined}>{notice}</div>
        {loadFailed ? (
          <>
            <p className="form-error" role="alert">Unable to load partnership managers.</p>
            <button type="button" className="btn secondary small" onClick={reload}>Retry</button>
          </>
        ) : data === null ? (
          <p className="muted" role="status">Loading partnership managers…</p>
        ) : data.total === 0 ? (
          <p className="empty" role="status">{query ? `No partnership managers match “${query}”.` : "No partnership managers yet. Use the Create partnership manager form to add the first one."}</p>
        ) : data.items.length === 0 ? (
          <>
            <p className="empty" role="status">This page is past the end of the list.</p>
            <button type="button" className="btn secondary small" onClick={() => go(0, query)}>Go to the first page</button>
          </>
        ) : (
          <>
            <div className="table-wrap" role="region" aria-label="Partnership managers" tabIndex={0}>
              <table>
                <thead>
                  <tr>
                    <th scope="col">Name</th><th scope="col">Employee ID</th><th scope="col">Head</th>
                    <th scope="col">Status</th><th scope="col"><span className="visually-hidden">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((r) => (
                    <AdminPartnershipRow key={r.id} row={r} onChanged={(text) => { setNotice(text); reload(); }} />
                  ))}
                </tbody>
              </table>
            </div>
            {data.total > PAGE_SIZE && (
              <nav aria-label="Partnership manager pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
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
