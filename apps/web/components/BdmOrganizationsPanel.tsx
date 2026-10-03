"use client";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";

import { isPage, type Page } from "@/lib/apiErrors";
import { display, LINK_STYLE, ORG_PAGE_SIZE, ORG_TYPE_LABEL, ORG_TYPES, ORGS_URL, type OrgRow } from "@/lib/bdmOrganizations";

// bdm-002 (spec §6.2, §12.2): the organization list for a BDM (their whole module, Q-02) or a manager (their team, C2). The API
// scopes the rows; nothing here filters for security. Filters and the page live in the URL (AdminBdmPanel's pattern), so refresh
// keeps the place and Back returns to the previous view. The current rows stay on screen while the next page loads.
type Filters = { offset: number; q: string; orgType: string; city: string; mine: boolean; archived: boolean };

function readFilters(params: URLSearchParams): Filters {
  const n = Number.parseInt(params.get("offset") ?? "", 10);
  return {
    offset: Number.isFinite(n) && n > 0 ? n : 0,
    q: (params.get("q") ?? "").trim(),
    orgType: params.get("org_type") ?? "",
    city: (params.get("city") ?? "").trim(),
    mine: params.get("assigned") === "me",
    archived: params.get("archived") === "1",
  };
}

function toUrl(f: Filters): URLSearchParams {
  const next = new URLSearchParams();
  if (f.offset > 0) next.set("offset", String(f.offset));
  if (f.q) next.set("q", f.q);
  if (f.orgType) next.set("org_type", f.orgType);
  if (f.city) next.set("city", f.city);
  if (f.mine) next.set("assigned", "me");
  if (f.archived) next.set("archived", "1");
  return next;
}

function toApi(f: Filters): string {
  const query = new URLSearchParams({ limit: String(ORG_PAGE_SIZE), offset: String(f.offset) });
  if (f.q) query.set("q", f.q);
  if (f.orgType) query.set("org_type", f.orgType);
  if (f.city) query.set("city", f.city);
  if (f.mine) query.set("assigned", "me");
  if (f.archived) query.set("include_archived", "true");
  return `${ORGS_URL}?${query}`;
}

const CHECKBOX = { display: "flex", gap: 6, alignItems: "center", minHeight: 44 } as const;

export default function BdmOrganizationsPanel({ basePath, isBdm }: { basePath: string; isBdm: boolean }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const filters = readFilters(params);
  const key = toUrl(filters).toString();
  const [data, setData] = useState<Page<OrgRow> | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [version, setVersion] = useState(0);
  const [draftQ, setDraftQ] = useState(filters.q);
  const [draftCity, setDraftCity] = useState(filters.city);

  // Back/Forward change the URL without remounting: follow it.
  useEffect(() => {
    setDraftQ(filters.q);
    setDraftCity(filters.city);
  }, [filters.q, filters.city]);

  useEffect(() => {
    let live = true;
    setLoadFailed(false);
    setLoading(true);
    fetch(toApi(readFilters(new URLSearchParams(key))))
      .then(async (response) => {
        const body = await response.json().catch(() => null);
        if (!response.ok || !isPage<OrgRow>(body)) throw new Error("not a page");
        if (live) setData(body);
      })
      .catch(() => {
        if (live) setLoadFailed(true);
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [key, version]);

  function go(next: Partial<Filters>) {
    const url = toUrl({ ...filters, offset: 0, ...next });
    // browser QA-15: the router waits for a server round trip before the URL (and so the fetch) changes; show the wait from the click.
    if (url.toString() !== key) setLoading(true);
    router.push(url.size ? `${pathname}?${url}` : pathname, { scroll: false });
  }
  const filtered = Boolean(filters.q || filters.orgType || filters.city || filters.mine || filters.archived);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    go({ q: draftQ.trim(), city: draftCity.trim() });
  };

  return (
    <div className="action-card wide" aria-busy={loading && !loadFailed}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
        <h3>Organizations</h3>
        {isBdm && (
          <Link className="btn small" href={`${basePath}/new`}>
            Add organization
          </Link>
        )}
      </div>
      <form role="search" aria-label="Filter organizations" onSubmit={submit} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
        <div className="field" style={{ flex: "1 1 200px", margin: 0 }}>
          <label htmlFor="org-filter-q">Name or code</label>
          <input id="org-filter-q" type="search" value={draftQ} maxLength={200} onChange={(e) => setDraftQ(e.target.value)} />
        </div>
        <div className="field" style={{ flex: "1 1 160px", margin: 0 }}>
          <label htmlFor="org-filter-city">City</label>
          <input id="org-filter-city" type="search" value={draftCity} maxLength={120} autoComplete="address-level2" onChange={(e) => setDraftCity(e.target.value)} />
        </div>
        <div className="field" style={{ flex: "0 1 180px", margin: 0 }}>
          <label htmlFor="org-filter-type">Type</label>
          <select id="org-filter-type" value={filters.orgType} onChange={(e) => go({ orgType: e.target.value })}>
            <option value="">All types</option>
            {ORG_TYPES.map((t) => (
              <option key={t} value={t}>
                {ORG_TYPE_LABEL[t]}
              </option>
            ))}
          </select>
        </div>
        {isBdm && (
          <label style={CHECKBOX}>
            <input type="checkbox" checked={filters.mine} onChange={(e) => go({ mine: e.target.checked })} />
            Assigned to me
          </label>
        )}
        <label style={CHECKBOX}>
          <input type="checkbox" checked={filters.archived} onChange={(e) => go({ archived: e.target.checked })} />
          Show archived
        </label>
        <button type="submit" className="btn secondary small">
          Search
        </button>
        {filtered && (
          <button type="button" className="btn secondary small" onClick={() => go({ q: "", orgType: "", city: "", mine: false, archived: false })}>
            Clear filters
          </button>
        )}
      </form>
      {loadFailed ? (
        <>
          <p className="form-error" role="alert">
            Unable to load organizations.
          </p>
          <button type="button" className="btn secondary small" onClick={() => setVersion((v) => v + 1)}>
            Retry
          </button>
        </>
      ) : data === null ? (
        <p className="muted" role="status">
          Loading organizations…
        </p>
      ) : data.total === 0 ? (
        filtered ? (
          <p className="empty" role="status">
            No organizations match these filters.
          </p>
        ) : (
          <div role="status">
            <p className="empty">{isBdm ? "No organizations yet." : "Your team has no organizations yet."}</p>
            {isBdm && (
              <Link className="btn small" href={`${basePath}/new`}>
                Add organization
              </Link>
            )}
          </div>
        )
      ) : data.items.length === 0 ? (
        <>
          <p className="empty" role="status">
            This page is past the end of the list.
          </p>
          <button type="button" className="btn secondary small" onClick={() => go({})}>
            Go to the first page
          </button>
        </>
      ) : (
        <>
          {loading && (
            <p className="muted" role="status" style={{ margin: 0 }}>
              Updating organizations…
            </p>
          )}
          <div className="table-wrap" role="region" aria-label="Organizations" tabIndex={0} style={loading ? { opacity: 0.6 } : undefined}>
            <table style={{ overflowWrap: "anywhere" }}>
              {/* browser QA-01: one unbroken name or city must wrap, not push every other column out of view */}
              <thead>
                <tr>
                  <th scope="col">Code</th>
                  <th scope="col">Name</th>
                  <th scope="col">Type</th>
                  <th scope="col">City</th>
                  <th scope="col">Primary contact</th>
                  <th scope="col">Assigned BDM</th>
                  <th scope="col">Last meeting</th>
                  <th scope="col">Next meeting</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((r) => (
                  <tr key={r.id}>
                    <td style={{ whiteSpace: "nowrap" }}>{r.code}</td>
                    <td style={{ minWidth: 160 }}>
                      <Link href={`${basePath}/${r.id}`} style={LINK_STYLE}>
                        {r.name}
                      </Link>
                      {r.archived && (
                        <>
                          {" "}
                          <span className="badge">Archived</span>
                        </>
                      )}
                    </td>
                    <td>{ORG_TYPE_LABEL[r.org_type]}</td>
                    <td>{r.city}</td>
                    <td>{display(r.primary_contact?.name)}</td>
                    <td>
                      {r.assigned_bdm.full_name}
                      {!r.assigned_bdm.active && <span className="muted"> (inactive)</span>}
                    </td>
                    <td>{display(r.last_meeting_at)}</td>
                    <td>{display(r.next_meeting_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.total > ORG_PAGE_SIZE && (
            <nav aria-label="Organization pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
              <span className="muted" style={{ fontSize: 13 }}>
                Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}
              </span>
              <button type="button" className="btn secondary small" disabled={data.offset === 0} onClick={() => go({ offset: Math.max(0, filters.offset - ORG_PAGE_SIZE) })}>
                Previous
              </button>
              <button type="button" className="btn secondary small" disabled={data.offset + data.items.length >= data.total} onClick={() => go({ offset: filters.offset + ORG_PAGE_SIZE })}>
                Next
              </button>
            </nav>
          )}
        </>
      )}
    </div>
  );
}
