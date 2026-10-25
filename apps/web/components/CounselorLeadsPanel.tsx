"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useId, useState } from "react";

import ExportButtons from "@/components/ExportButtons";
import LocalTime from "@/components/LocalTime";
import { detailMessage, isPage, type Page } from "@/lib/apiErrors";
import { STAGES } from "@/lib/leadStages";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { COUNSELOR_LEADS_URL, counselorLeadHref, type CounselorLead } from "@/lib/leadHandover";

const PAGE_SIZE = 20;
const COUNSELOR_LEADS_EXPORT_URL = "/api/v1/counselor/exports/leads";
const PRIORITIES = [["hot", "Hot"], ["warm", "Warm"], ["cold", "Cold"]] as const;
const FILTER_KEYS = ["stage", "priority", "from", "to"] as const;
type FilterKey = (typeof FILTER_KEYS)[number];

/** tel-018 (spec §4): the leads handed to this counselor, newest first, 20 a page; the Lead ID opens the lead (return, student link).
 *  ccrm-012 (DEC-SCOPE-246 QS7): Stage, Priority and lead-date filters, kept in the URL (a reload or a shared link keeps them). */
export default function CounselorLeadsPanel({ division }: { division: "it" | "overseas" }) {
  const idp = useId();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const filters = new URLSearchParams(FILTER_KEYS.flatMap((key) => (searchParams.get(key) ? [[key, searchParams.get(key) as string]] : [])));
  const filterQuery = filters.toString();
  const [page, setPage] = useState<Page<CounselorLead> | { failed: string } | null>(null);
  const [offset, setOffset] = useState(0);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
    new URLSearchParams(filterQuery).forEach((value, key) => params.set(key, value));
    fetch(`${COUNSELOR_LEADS_URL}?${params}`, { signal: controller.signal })
      .then(async (response) => {
        const data = await response.json().catch(() => null);
        // A refused filter (422) says why, so the counselor can change or clear it.
        if (response.status === 422) return setPage({ failed: detailMessage(data?.detail) });
        if (!response.ok || !isPage<CounselorLead>(data)) throw new Error(`Request failed (${response.status})`);
        setPage(data);
      })
      .catch(() => controller.signal.aborted || setPage({ failed: "" }));
    return () => controller.abort();
  }, [offset, attempt, filterQuery]);

  function filterBy(key: FilterKey, value: string) {
    const next = new URLSearchParams(filterQuery);
    if (value) next.set(key, value);
    else next.delete(key);
    setOffset(0);
    setPage(null);
    router.replace(next.size ? `${pathname}?${next}` : pathname);
  }

  const filtered = filterQuery !== "";
  let body: React.ReactNode;
  if (page === null) body = <p className="muted" role="status">Loading leads…</p>;
  else if ("failed" in page) {
    body = page.failed ? (
      <p className="form-error" role="alert">{page.failed}</p>
    ) : (
      <p className="form-error" role="alert">
        Unable to load your leads. <button type="button" className="btn secondary small" onClick={() => { setPage(null); setAttempt((n) => n + 1); }}>Try again</button>
      </p>
    );
  } else if (page.items.length === 0) body = <p className="muted">{filtered ? "No leads match these filters." : "No leads have been handed to you yet."}</p>;
  else {
    body = (
      <>
        <div className="table-wrap workspace" role="region" aria-label="Leads handed to you" tabIndex={0}>
          <table className="table">
            <thead><tr><th scope="col">Lead ID</th><th scope="col">Name</th><th scope="col">Interest</th><th scope="col">Stage</th><th scope="col">Telecaller</th><th scope="col">Lead date</th></tr></thead>
            <tbody>
              {page.items.map((lead) => (
                <tr key={lead.id}>
                  <th scope="row"><Link href={counselorLeadHref(division, lead.id)} style={LINK_STYLE}>{lead.lead_code}</Link></th>
                  <td>{lead.name}</td>
                  <td>{lead.subject}</td>
                  <td>{lead.status_label}</td>
                  <td>{lead.telecaller?.full_name ?? <span className="muted">Unassigned</span>}</td>
                  <td><LocalTime value={lead.created_at} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <nav aria-label="Lead pages" style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
          <span className="muted" style={{ fontSize: 13 }}>{page.offset + 1}–{page.offset + page.items.length} of {page.total}</span>
          {page.offset > 0 && <button type="button" className="btn secondary small" onClick={() => setOffset(Math.max(0, page.offset - PAGE_SIZE))}>Previous</button>}
          {page.offset + page.items.length < page.total && <button type="button" className="btn secondary small" onClick={() => setOffset(page.offset + PAGE_SIZE)}>Next</button>}
        </nav>
        {/* ccrm-035 (DEC-SCOPE-268 E3): every lead matching the filters, not just this page; overseas only. */}
        {division === "overseas" && <ExportButtons url={filterQuery ? `${COUNSELOR_LEADS_EXPORT_URL}?${filterQuery}` : COUNSELOR_LEADS_EXPORT_URL} filename="my-leads" label="Export my leads" />}
      </>
    );
  }
  return (
    <section aria-labelledby={`${idp}-heading`} className="portal-content" style={{ display: "grid", gap: 12 }}>
      <div className="portal-title">
        <div>
          <div className="eyebrow">Leads</div>
          <h2 id={`${idp}-heading`}>My leads</h2>
          <p className="muted">
            {division === "overseas" ? "Leads telecallers handed to you and walk-ins you recorded." : "Leads telecallers handed to you."} Open one to link the
            student account or return it to the telecaller.
          </p>
        </div>
        {/* csc-004 (DEC-SCOPE-229, W1): only the overseas counselor records a walk-in as a lead. */}
        {division === "overseas" && <Link className="btn" href="/overseas/counselor/leads/new">New walk-in lead</Link>}
      </div>
      <form className="form filter-bar" aria-label="Filter leads" onSubmit={(event) => event.preventDefault()} style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "end" }}>
        <div className="field">
          <label htmlFor={`${idp}-stage`}>Stage</label>
          <select id={`${idp}-stage`} value={filters.get("stage") ?? ""} onChange={(event) => filterBy("stage", event.target.value)}>
            <option value="">All</option>
            {STAGES.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor={`${idp}-priority`}>Priority</label>
          <select id={`${idp}-priority`} value={filters.get("priority") ?? ""} onChange={(event) => filterBy("priority", event.target.value)}>
            <option value="">All</option>
            {PRIORITIES.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor={`${idp}-from`}>Lead date from</label>
          <input id={`${idp}-from`} type="date" value={filters.get("from") ?? ""} max={filters.get("to") ?? undefined} onChange={(event) => filterBy("from", event.target.value)} />
        </div>
        <div className="field">
          <label htmlFor={`${idp}-to`}>Lead date to</label>
          <input id={`${idp}-to`} type="date" value={filters.get("to") ?? ""} min={filters.get("from") ?? undefined} onChange={(event) => filterBy("to", event.target.value)} />
        </div>
        {filtered && <Link href={pathname} onClick={() => { setOffset(0); setPage(null); }}>Clear filters</Link>}
      </form>
      {body}
    </section>
  );
}
