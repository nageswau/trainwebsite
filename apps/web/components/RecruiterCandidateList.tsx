"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import type { Page } from "@/lib/apiErrors";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import LocalTime from "@/components/LocalTime";
import { activeValues, type CatalogueValue } from "@/lib/recruiterCatalogue";
import { CANDIDATES_PATH, CANDIDATES_URL, STATUSES, STATUS_LABEL, experienceLabel, type CandidateItem } from "@/lib/recruiterCandidates";
import { pageOffset } from "@/lib/telecaller";
import { getPage } from "@/lib/telecallerCatalogue";

const PAGE_SIZE = 50;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** rec-009 (spec §6; AC2, S2-§13): the candidate list -- the source on every row. The source picker reads the recruiter catalogue,
 *  which is closed to hr_team (rec-002 C3), so a read-only role gets no picker (QA-03). Search, filters and page live in the URL, so refresh
 *  keeps the place and Back returns to the previous view (the tel-008 list idiom). A hand-edited value the API would refuse is ignored. */
export default function RecruiterCandidateList({ sourceFilter }: { sourceFilter: boolean }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const query = (params.get("q") ?? "").trim();
  const offset = pageOffset(params.get("offset") ?? undefined);
  const status = STATUSES.some((s) => s.key === params.get("status")) ? params.get("status")! : "";
  const sourceId = UUID.test(params.get("source_id") ?? "") ? params.get("source_id")! : "";
  const archived = params.get("archived") === "true";
  const request = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
  for (const [key, value] of Object.entries({ q: query, status, source_id: sourceId, archived: archived ? "true" : "" })) if (value) request.set(key, value);
  const requestUrl = `${CANDIDATES_URL}?${request}`;
  const filtered = !!(query || status || sourceId);

  const [data, setData] = useState<Page<CandidateItem> | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [draft, setDraft] = useState(query);
  const [sources, setSources] = useState<CatalogueValue[]>([]);
  useEffect(() => setDraft(query), [query]);

  useEffect(() => {
    const controller = new AbortController();
    setLoadFailed(false);
    getPage<CandidateItem>(requestUrl, controller.signal).then(setData).catch(() => controller.signal.aborted || setLoadFailed(true));
    return () => controller.abort();
  }, [requestUrl, version]);

  useEffect(() => {
    if (!sourceFilter) return;
    const controller = new AbortController(); // a picker that fails to load leaves just "All sources"; the rest keeps working
    activeValues("candidate-sources", controller.signal).then(setSources).catch(() => undefined);
    return () => controller.abort();
  }, [sourceFilter]);

  /** A new filter or search starts again from the first page; only the pager passes an offset. */
  function go(changes: Record<string, string>, nextOffset = 0) {
    const next = new URLSearchParams(params.toString());
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    if (nextOffset > 0) next.set("offset", String(nextOffset));
    else next.delete("offset");
    router.push(next.size ? `${pathname}?${next}` : pathname, { scroll: false });
  }

  return (
    <div className="action-card" aria-busy={data === null && !loadFailed}>
      <form role="search" onSubmit={(e) => { e.preventDefault(); go({ q: draft.trim() }); }} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
        <div className="field" style={{ flex: "1 1 16rem", minWidth: 0, marginBottom: 0 }}>
          <label htmlFor="cand-search">Search candidates</label>
          <span id="cand-search-hint" className="muted" style={{ fontSize: 13 }}>Name, candidate ID, email or mobile</span>
          <input id="cand-search" className="search" type="search" aria-describedby="cand-search-hint" value={draft} maxLength={200} onChange={(e) => setDraft(e.target.value)} />
        </div>
        <button type="submit" className="btn secondary small">Search</button>
        {query && <button type="button" className="btn secondary small" onClick={() => go({ q: "" })}>Clear search</button>}
      </form>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginTop: 8, alignItems: "flex-end" }}>
        {sourceFilter && <div className="field" style={{ flex: "1 1 10rem" }}>
          <label htmlFor="cand-filter-source">Source</label>
          <select id="cand-filter-source" value={sourceId} onChange={(e) => go({ source_id: e.target.value })}>
            <option value="">All sources</option>
            {sources.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>}
        <div className="field" style={{ flex: "1 1 10rem" }}>
          <label htmlFor="cand-filter-status">Status</label>
          <select id="cand-filter-status" value={status} onChange={(e) => go({ status: e.target.value })}>
            <option value="">All statuses</option>
            {STATUSES.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
          </select>
        </div>
        <label style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 12 }}>
          <input type="checkbox" checked={archived} onChange={(e) => go({ archived: e.target.checked ? "true" : "" })} /> Show archived only
        </label>
      </div>
      {loadFailed ? (
        <div style={{ marginTop: 12 }}>
          <p className="form-error" role="alert">Unable to load candidates.</p>
          <button type="button" className="btn secondary small" onClick={() => setVersion((v) => v + 1)}>Retry</button>
        </div>
      ) : data === null ? (
        <p className="muted" role="status" style={{ marginTop: 12 }}>Loading candidates…</p>
      ) : data.items.length === 0 ? (
        <p className="muted" role="status" style={{ marginTop: 12 }}>
          {filtered ? "No candidates match these filters." : archived ? "No archived candidates." : "No candidates yet."}
        </p>
      ) : (
        <>
          <div className="table-scroll" style={{ marginTop: 12 }}>
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Name</th>
                  <th scope="col">Candidate ID</th>
                  <th scope="col">Source</th>
                  <th scope="col">Preferred role</th>
                  <th scope="col">Experience</th>
                  <th scope="col">Location</th>
                  <th scope="col">Status</th>
                  <th scope="col">Added</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((c) => (
                  <tr key={c.id}>
                    <th scope="row"><Link href={`${CANDIDATES_PATH}/${encodeURIComponent(c.id)}`} style={LINK_STYLE}>{c.name}</Link></th>
                    <td style={{ whiteSpace: "nowrap" }}>{c.candidate_code}</td>
                    <td>
                      {c.source.name}
                      {c.source_detail && <div className="muted" style={{ fontSize: 13, overflowWrap: "anywhere" }}>{c.source_detail}</div>}
                    </td>
                    <td>{c.preferred_role ?? <span className="muted">—</span>}</td>
                    <td style={{ whiteSpace: "nowrap" }}>{experienceLabel(c.experience_months)}</td>
                    <td>{c.location ?? <span className="muted">—</span>}</td>
                    <td>{STATUS_LABEL[c.status] ?? c.status}{c.archived && <div className="muted" style={{ fontSize: 13 }}>Archived</div>}</td>
                    <td style={{ whiteSpace: "nowrap" }}><LocalTime value={c.created_at} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.total > PAGE_SIZE && (
            <nav aria-label="Candidate pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
              <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
              <button type="button" className="btn secondary small" aria-label="Previous page" disabled={offset === 0} onClick={() => go({}, Math.max(0, offset - PAGE_SIZE))}>Previous</button>
              <button type="button" className="btn secondary small" aria-label="Next page" disabled={data.offset + data.items.length >= data.total} onClick={() => go({}, offset + PAGE_SIZE)}>Next</button>
            </nav>
          )}
        </>
      )}
    </div>
  );
}
