"use client";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";

import { isPage, type Page } from "@/lib/apiErrors";
import { CHECKBOX_ROW, display, LINK_STYLE } from "@/lib/bdmOrganizations";
import { activeValues, type CatalogueValue } from "@/lib/recruiterCatalogue";
import { COMPANIES_PATH, COMPANIES_URL, type CompanyRow, personName, PRIORITIES, PRIORITY_LABEL } from "@/lib/recruiterCompanies";
import { PAGE_SIZE } from "@/lib/telecaller";

// rec-003 (spec §6): the company list for a recruiter (their own), a manager (their team's plus the unassigned queue) or super admin.
// The API scopes the rows. Filters and the page live in the URL (BdmOrganizationsPanel's pattern), so refresh keeps the place and Back
// returns to the previous view; the current rows stay on screen while the next page loads. Below 980px each row is a card of labelled
// lines (the house `.telecaller-list` layout, QA-02).
type Filters = { offset: number; q: string; city: string; priority: string; leadSource: string; industry: string; assigned: string; archived: boolean };
type Team = { id: string; full_name: string; active: boolean }[];

function readFilters(params: URLSearchParams): Filters {
  const n = Number.parseInt(params.get("offset") ?? "", 10);
  const priority = params.get("priority") ?? "";
  return {
    offset: Number.isFinite(n) && n > 0 ? n : 0,
    q: (params.get("q") ?? "").trim(),
    city: (params.get("city") ?? "").trim(),
    priority: (PRIORITIES as string[]).includes(priority) ? priority : "", // a hand-edited URL never 422s
    leadSource: params.get("lead_source_id") ?? "",
    industry: params.get("industry_id") ?? "",
    assigned: params.get("assigned") ?? "",
    archived: params.get("archived") === "1",
  };
}

function toUrl(f: Filters): URLSearchParams {
  const next = new URLSearchParams();
  if (f.offset > 0) next.set("offset", String(f.offset));
  if (f.q) next.set("q", f.q);
  if (f.city) next.set("city", f.city);
  if (f.priority) next.set("priority", f.priority);
  if (f.leadSource) next.set("lead_source_id", f.leadSource);
  if (f.industry) next.set("industry_id", f.industry);
  if (f.assigned) next.set("assigned", f.assigned);
  if (f.archived) next.set("archived", "1");
  return next;
}

function toApi(f: Filters): string {
  const query = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(f.offset) });
  for (const [name, value] of toUrl({ ...f, offset: 0 })) query.set(name === "archived" ? "include_archived" : name, name === "archived" ? "true" : value);
  return `${COMPANIES_URL}?${query}`;
}

function Picker({ id, label, value, all, options, onChange }: { id: string; label: string; value: string; all: string; options: { id: string; name: string }[]; onChange: (v: string) => void }) {
  return (
    <div className="field" style={{ flex: "0 1 180px", margin: 0 }}>
      <label htmlFor={id}>{label}</label>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{all}</option>
        {options.map((o) => (
          <option key={o.id} value={o.id}>
            {o.name}
          </option>
        ))}
      </select>
    </div>
  );
}

export default function RecruiterCompaniesPanel({ canCreate, isManager = false }: { canCreate: boolean; isManager?: boolean }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const filters = readFilters(params);
  const key = toUrl(filters).toString();
  const [data, setData] = useState<Page<CompanyRow> | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [fetching, setFetching] = useState(true);
  const [target, setTarget] = useState<string | null>(null);
  const loading = fetching || (target !== null && target !== key);
  const [version, setVersion] = useState(0);
  const [draftQ, setDraftQ] = useState(filters.q);
  const [draftCity, setDraftCity] = useState(filters.city);
  const [sources, setSources] = useState<CatalogueValue[]>([]);
  const [industries, setIndustries] = useState<CatalogueValue[]>([]);
  const [team, setTeam] = useState<Team>([]);

  useEffect(() => {
    setDraftQ(filters.q);
    setDraftCity(filters.city);
  }, [filters.q, filters.city]);

  // The filter pickers: a failed read leaves a picker with only "All" (the list itself still works).
  useEffect(() => {
    const abort = new AbortController();
    activeValues("lead-sources", abort.signal).then(setSources, () => undefined);
    activeValues("industries", abort.signal).then(setIndustries, () => undefined);
    if (isManager) {
      fetch("/api/v1/recruiter/manager/team?limit=100", { signal: abort.signal })
        .then((r) => (r.ok ? r.json() : null))
        .then((body) => body && setTeam(body.items), () => undefined);
    }
    return () => abort.abort();
  }, [isManager]);

  useEffect(() => {
    let live = true;
    setLoadFailed(false);
    setFetching(true);
    setTarget(null);
    fetch(toApi(readFilters(new URLSearchParams(key))))
      .then(async (response) => {
        const body = await response.json().catch(() => null);
        if (!response.ok || !isPage<CompanyRow>(body)) throw new Error("not a page");
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
  const filtered = Boolean(filters.q || filters.city || filters.priority || filters.leadSource || filters.industry || filters.assigned || filters.archived);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    go({ q: draftQ.trim(), city: draftCity.trim() });
  };
  const addLink = canCreate && (
    <Link className="btn small" href={`${COMPANIES_PATH}/new`}>
      Add company
    </Link>
  );

  return (
    <div className="action-card wide telecaller-list" aria-busy={loading && !loadFailed}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
        <h3>Companies</h3>
        {addLink}
      </div>
      <form role="search" aria-label="Filter companies" onSubmit={submit} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
        <div className="field" style={{ flex: "1 1 200px", margin: 0 }}>
          <label htmlFor="company-filter-q">Name or code</label>
          <input id="company-filter-q" type="search" value={draftQ} maxLength={200} onChange={(e) => setDraftQ(e.target.value)} />
        </div>
        <div className="field" style={{ flex: "1 1 160px", margin: 0 }}>
          <label htmlFor="company-filter-city">City</label>
          <input id="company-filter-city" type="search" value={draftCity} maxLength={120} onChange={(e) => setDraftCity(e.target.value)} />
        </div>
        <Picker id="company-filter-priority" label="Priority" value={filters.priority} all="All priorities" options={PRIORITIES.map((p) => ({ id: p, name: PRIORITY_LABEL[p] }))} onChange={(v) => go({ priority: v })} />
        <Picker id="company-filter-source" label="Lead source" value={filters.leadSource} all="All sources" options={sources} onChange={(v) => go({ leadSource: v })} />
        <Picker id="company-filter-industry" label="Industry" value={filters.industry} all="All industries" options={industries} onChange={(v) => go({ industry: v })} />
        {isManager && (
          <Picker
            id="company-filter-assigned"
            label="Recruiter"
            value={filters.assigned}
            all="Anyone"
            options={[{ id: "unassigned", name: "Unassigned" }, ...team.map((r) => ({ id: r.id, name: personName({ ...r }) }))]}
            onChange={(v) => go({ assigned: v })}
          />
        )}
        <label style={CHECKBOX_ROW}>
          <input type="checkbox" checked={filters.archived} onChange={(e) => go({ archived: e.target.checked })} />
          Show archived
        </label>
        <button type="submit" className="btn secondary small">
          Search
        </button>
        {filtered && (
          <button type="button" className="btn secondary small" onClick={() => go({ q: "", city: "", priority: "", leadSource: "", industry: "", assigned: "", archived: false })}>
            Clear filters
          </button>
        )}
      </form>
      {loadFailed ? (
        <>
          <p className="form-error" role="alert">
            Unable to load companies.
          </p>
          <button type="button" className="btn secondary small" onClick={() => setVersion((v) => v + 1)}>
            Retry
          </button>
        </>
      ) : data === null ? (
        <p className="muted" role="status">
          Loading companies…
        </p>
      ) : data.total === 0 ? (
        filtered ? (
          <p className="empty" role="status">
            No companies match these filters.
          </p>
        ) : (
          <div role="status">
            <p className="empty">No companies yet.</p>
            {addLink}
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
              Updating companies…
            </p>
          )}
          <div className="table-wrap" role="region" aria-label="Companies" tabIndex={0} style={loading ? { opacity: 0.6 } : undefined}>
            <table style={{ width: "100%", overflowWrap: "anywhere" }}>
              <thead>
                <tr>
                  <th scope="col">Code</th>
                  <th scope="col">Company</th>
                  <th scope="col">City</th>
                  <th scope="col">Priority</th>
                  <th scope="col">Lead source</th>
                  <th scope="col">Industry</th>
                  <th scope="col">Recruiter</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((r) => (
                  <tr key={r.id}>
                    <td data-label="Code" style={{ whiteSpace: "nowrap" }}>{r.code}</td>
                    <td data-label="Name" style={{ minWidth: 160 }}>
                      <Link href={`${COMPANIES_PATH}/${r.id}`} style={LINK_STYLE}>
                        {r.name}
                      </Link>
                      {r.archived && (
                        <>
                          {" "}
                          <span className="badge">Archived</span>
                        </>
                      )}
                    </td>
                    <td data-label="City">{display(r.city)}</td>
                    <td data-label="Priority">{r.priority ? PRIORITY_LABEL[r.priority] : "—"}</td>
                    <td data-label="Lead source">{display(r.lead_source?.name)}</td>
                    <td data-label="Industry">{display(r.industry?.name)}</td>
                    <td data-label="Recruiter">{personName(r.assigned_recruiter)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.total > PAGE_SIZE && (
            <nav aria-label="Company pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
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
