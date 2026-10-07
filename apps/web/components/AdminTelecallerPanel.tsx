"use client";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import AdminTelecallerCreateForm from "@/components/AdminTelecallerCreateForm";
import AdminTelecallerManagersCard from "@/components/AdminTelecallerManagersCard";
import AdminTelecallerRow from "@/components/AdminTelecallerRow";
import CreateJumpLink from "@/components/CreateJumpLink";
import { isPage, type Page } from "@/lib/apiErrors";
import { MANAGERS_URL, PAGE_SIZE, TELECALLERS_URL, type TelecallerAdminRow } from "@/lib/telecaller";

// tel-001 (spec §6.3): the admin's telecaller list -- loading / error+Retry / empty / pager, the AdminBdmPanel pattern. The API scopes
// rows to the teams this admin manages (T21); nothing here filters for security. Page and search live in the URL (?offset=&q=), so
// refresh keeps the place and Back returns to the previous page; a newly created telecaller is shown by filtering to its Employee ID.
function urlOffset(raw: string | null): number {
  const n = Number.parseInt(raw ?? "", 10);
  return Number.isFinite(n) && n > 0 ? n : 0;
}

async function fetchPage<T>(url: string): Promise<Page<T>> {
  const response = await fetch(url);
  const body = await response.json().catch(() => null);
  if (!response.ok || !isPage<T>(body)) throw new Error("not a page");
  return body;
}

export default function AdminTelecallerPanel({ role }: { role: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const fromUrl = { offset: urlOffset(params.get("offset")), query: (params.get("q") ?? "").trim() };
  const [data, setData] = useState<Page<TelecallerAdminRow> | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [offset, setOffset] = useState(fromUrl.offset);
  const [query, setQuery] = useState(fromUrl.query);
  const [draft, setDraft] = useState(fromUrl.query);
  const [version, setVersion] = useState(0);
  const [managersAvailable, setManagersAvailable] = useState<boolean | null>(null);
  const [managersFailed, setManagersFailed] = useState(false);
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
    fetchPage<TelecallerAdminRow>(`${TELECALLERS_URL}?${request}`).then(setData).catch(() => setLoadFailed(true));
  }, [offset, query, version]);

  // Only "is there any active manager?" -- the picker itself searches the server. A failed check is not "no managers".
  const checkManagers = useCallback(() => {
    setManagersFailed(false);
    setManagersAvailable(null);
    fetchPage(`${MANAGERS_URL}?limit=1`)
      .then((page) => setManagersAvailable(page.total > 0))
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
          <p className="form-error" role="alert">Unable to load telecaller managers.</p>
          <button type="button" className="btn secondary small" onClick={checkManagers}>Retry loading managers</button>
        </div>
      )}
      <AdminTelecallerCreateForm role={role} managersAvailable={managersAvailable} onCreated={(employeeId) => { search(employeeId); reload(); }} />
      <div className="action-card wide telecaller-list" aria-busy={data === null && !loadFailed}>
        <h3>Telecallers</h3>
        <CreateJumpLink targetId="tel-name" label="Create telecaller" />
        <form role="search" onSubmit={(event) => { event.preventDefault(); search(draft); }} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
          <input type="search" aria-label="Search telecallers" placeholder="Name, email or Employee ID" value={draft} maxLength={200} onChange={(event) => setDraft(event.target.value)} style={{ flex: "1 1 220px" }} />
          <button type="submit" className="btn secondary small">Search</button>
          {query && <button type="button" className="btn secondary small" onClick={() => search("")}>Clear search</button>}
        </form>
        <div className={notice ? "form-message" : undefined} role="status" aria-live="polite" style={notice ? { marginBottom: 8 } : undefined}>{notice}</div>
        {loadFailed ? (
          <>
            <p className="form-error" role="alert">Unable to load telecallers.</p>
            <button type="button" className="btn secondary small" onClick={reload}>Retry</button>
          </>
        ) : data === null ? (
          <p className="muted" role="status">Loading telecallers…</p>
        ) : data.total === 0 ? (
          <p className="empty" role="status">{query ? `No telecallers match “${query}”.` : "No telecallers yet. Use the Create telecaller form to add the first one."}</p>
        ) : data.items.length === 0 ? (
          <>
            <p className="empty" role="status">This page is past the end of the list.</p>
            <button type="button" className="btn secondary small" onClick={() => go(0, query)}>Go to the first page</button>
          </>
        ) : (
          <>
            <div className="table-wrap" role="region" aria-label="Telecallers" tabIndex={0}>
              <table>
                <thead>
                  <tr>
                    <th scope="col">Name</th><th scope="col">Employee ID</th><th scope="col">Team</th>
                    <th scope="col">Manager</th><th scope="col">Status</th><th scope="col"><span className="visually-hidden">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((r) => (
                    <AdminTelecallerRow key={r.id} row={r} role={role} onChanged={(text) => { setNotice(text); reload(); }} />
                  ))}
                </tbody>
              </table>
            </div>
            {data.total > PAGE_SIZE && (
              <nav aria-label="Telecaller pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
                <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
                <button type="button" className="btn secondary small" aria-label="Previous page" disabled={data.offset === 0} onClick={() => go(Math.max(0, offset - PAGE_SIZE), query)}>Previous</button>
                <button type="button" className="btn secondary small" aria-label="Next page" disabled={data.offset + data.items.length >= data.total} onClick={() => go(offset + PAGE_SIZE, query)}>Next</button>
              </nav>
            )}
          </>
        )}
      </div>
      {role === "super_admin" && <AdminTelecallerManagersCard onChanged={(text) => { setNotice(text); reload(); }} />}
    </>
  );
}
