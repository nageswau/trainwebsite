"use client";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";

import { isPage, type Page } from "@/lib/apiErrors";
import { PAGE_SIZE } from "@/lib/bdm";
import { BOARD_LABEL, BOARDS, CHECKBOX_ROW, display, LINK_STYLE, ORG_TYPE_LABEL, ORG_TYPES, ORGS_URL, type OrgRow, profileGroup } from "@/lib/bdmOrganizations";

// bdm-002 (spec §6.2, §12.2): the organization list for a BDM (their whole module, Q-02) or a manager (their team, C2). The API
// scopes the rows; nothing here filters for security. Filters and the page live in the URL (AdminBdmPanel's pattern), so refresh
// keeps the place and Back returns to the previous view. The current rows stay on screen while the next page loads.
// bdm-003 (spec §6.3): Board / Affiliation / Territory appear with the Type they belong to and are dropped when it changes.
type Filters = { offset: number; q: string; orgType: string; city: string; board: string; affiliation: string; territory: string; mine: boolean; archived: boolean };

// bdm-003: the one profile filter each Type group has (spec §6.3).
const PROFILE_FILTER = { school: "board", college: "affiliation", agent: "territory" } as const;
type ProfileFilter = (typeof PROFILE_FILTER)[keyof typeof PROFILE_FILTER];

/** The single place that decides which profile filter applies: only the one that belongs to the Type, so every applied filter has a
 * visible control (browser QA3-01), and only a known Board, so the API never 422s on a hand-edited URL (QA3-02). Used when reading and
 * when writing the URL, so a Type change or Search can pass every draft and the stale ones simply drop out. */
function forType(f: Filters): Filters {
  const group = profileGroup(f.orgType);
  const own: ProfileFilter | null = group ? PROFILE_FILTER[group] : null;
  const keep = (key: ProfileFilter) => (key === own ? f[key] : "");
  return { ...f, board: (BOARDS as readonly string[]).includes(f.board) ? keep("board") : "", affiliation: keep("affiliation"), territory: keep("territory") };
}

function readFilters(params: URLSearchParams): Filters {
  const n = Number.parseInt(params.get("offset") ?? "", 10);
  return forType({
    offset: Number.isFinite(n) && n > 0 ? n : 0,
    q: (params.get("q") ?? "").trim(),
    orgType: params.get("org_type") ?? "",
    city: (params.get("city") ?? "").trim(),
    board: params.get("board") ?? "",
    affiliation: (params.get("affiliation") ?? "").trim(),
    territory: (params.get("territory") ?? "").trim(),
    mine: params.get("assigned") === "me",
    archived: params.get("archived") === "1",
  });
}

function toUrl(filters: Filters): URLSearchParams {
  const f = forType(filters);
  const next = new URLSearchParams();
  if (f.offset > 0) next.set("offset", String(f.offset));
  if (f.q) next.set("q", f.q);
  if (f.orgType) next.set("org_type", f.orgType);
  if (f.city) next.set("city", f.city);
  if (f.board) next.set("board", f.board);
  if (f.affiliation) next.set("affiliation", f.affiliation);
  if (f.territory) next.set("territory", f.territory);
  if (f.mine) next.set("assigned", "me");
  if (f.archived) next.set("archived", "1");
  return next;
}

/** The API query for the same filters: the page params first, the URL's filters as they are, `archived=1` spelled as the API's flag. */
function toApi(f: Filters): string {
  const query = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(f.offset) });
  for (const [name, value] of toUrl({ ...f, offset: 0 })) {
    if (name === "archived") query.set("include_archived", "true");
    else query.set(name, value);
  }
  return `${ORGS_URL}?${query}`;
}

export default function BdmOrganizationsPanel({ basePath, isBdm }: { basePath: string; isBdm: boolean }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const filters = readFilters(params);
  const key = toUrl(filters).toString();
  const [data, setData] = useState<Page<OrgRow> | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [fetching, setFetching] = useState(true);
  // Browser QA-15: the router waits for a server round trip before the URL (and so the fetch) changes, so the wait is shown from the
  // click: busy while a requested URL hasn't landed. Derived, so undoing a change before it lands can't leave it stuck (simplify A6).
  const [target, setTarget] = useState<string | null>(null);
  const loading = fetching || (target !== null && target !== key);
  const [version, setVersion] = useState(0);
  const [draftQ, setDraftQ] = useState(filters.q);
  const [draftCity, setDraftCity] = useState(filters.city);
  const [draftAffiliation, setDraftAffiliation] = useState(filters.affiliation);
  const [draftTerritory, setDraftTerritory] = useState(filters.territory);
  const group = profileGroup(filters.orgType);

  // Back/Forward change the URL without remounting: follow it.
  useEffect(() => {
    setDraftQ(filters.q);
    setDraftCity(filters.city);
    setDraftAffiliation(filters.affiliation);
    setDraftTerritory(filters.territory);
  }, [filters.q, filters.city, filters.affiliation, filters.territory]);

  useEffect(() => {
    let live = true;
    setLoadFailed(false);
    setFetching(true);
    setTarget(null); // the URL has moved (a filter landed, or Back/Forward): any earlier target is settled
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
        if (live) setFetching(false);
      });
    return () => {
      live = false;
    };
  }, [key, version]);

  function go(next: Partial<Filters>) {
    const url = toUrl({ ...filters, offset: 0, ...next });
    setTarget(url.toString());
    router.push(url.size ? `${pathname}?${url}` : pathname, { scroll: false });
  }
  const filtered = Boolean(filters.q || filters.orgType || filters.city || filters.board || filters.affiliation || filters.territory || filters.mine || filters.archived);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    go({ q: draftQ.trim(), city: draftCity.trim(), affiliation: draftAffiliation.trim(), territory: draftTerritory.trim() }); // forType drops the other type's
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
        {group === "school" && (
          <div className="field" style={{ flex: "0 1 160px", margin: 0 }}>
            <label htmlFor="org-filter-board">Board</label>
            <select id="org-filter-board" value={filters.board} onChange={(e) => go({ board: e.target.value })}>
              <option value="">All boards</option>
              {BOARDS.map((b) => (
                <option key={b} value={b}>
                  {BOARD_LABEL[b]}
                </option>
              ))}
            </select>
          </div>
        )}
        {group === "college" && (
          <div className="field" style={{ flex: "1 1 160px", margin: 0 }}>
            <label htmlFor="org-filter-affiliation">University / affiliation</label>
            <input id="org-filter-affiliation" type="search" value={draftAffiliation} maxLength={200} onChange={(e) => setDraftAffiliation(e.target.value)} />
          </div>
        )}
        {group === "agent" && (
          <div className="field" style={{ flex: "1 1 160px", margin: 0 }}>
            <label htmlFor="org-filter-territory">Territory</label>
            <input id="org-filter-territory" type="search" value={draftTerritory} maxLength={120} onChange={(e) => setDraftTerritory(e.target.value)} />
          </div>
        )}
        {isBdm && (
          <label style={CHECKBOX_ROW}>
            <input type="checkbox" checked={filters.mine} onChange={(e) => go({ mine: e.target.checked })} />
            Assigned to me
          </label>
        )}
        <label style={CHECKBOX_ROW}>
          <input type="checkbox" checked={filters.archived} onChange={(e) => go({ archived: e.target.checked })} />
          Show archived
        </label>
        <button type="submit" className="btn secondary small">
          Search
        </button>
        {filtered && (
          <button type="button" className="btn secondary small" onClick={() => go({ q: "", orgType: "", city: "", board: "", affiliation: "", territory: "", mine: false, archived: false })}>
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
          {data.total > PAGE_SIZE && (
            <nav aria-label="Organization pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
              <span className="muted" style={{ fontSize: 13 }}>
                Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}
              </span>
              <button type="button" className="btn secondary small" disabled={data.offset === 0} onClick={() => go({ offset: Math.max(0, filters.offset - PAGE_SIZE) })}>
                Previous
              </button>
              <button type="button" className="btn secondary small" disabled={data.offset + data.items.length >= data.total} onClick={() => go({ offset: filters.offset + PAGE_SIZE })}>
                Next
              </button>
            </nav>
          )}
        </>
      )}
    </div>
  );
}
