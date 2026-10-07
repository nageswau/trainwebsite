"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import ProductOptions from "@/components/TelecallerProductOptions";
import type { Page } from "@/lib/apiErrors";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { formatDate } from "@/lib/formatDate";
import { STAGES } from "@/lib/leadStages";
import { pageOffset } from "@/lib/telecaller";
import { activeCampaigns, activeProducts, getPage, type Campaign, type Product } from "@/lib/telecallerCatalogue";
import { FOLLOW_UP_FILTERS, LEAD_LIST_FILTERS, LEADS_URL, PRIORITIES, PRIORITY_LABEL, type LeadListFilter, type TelecallerLead } from "@/lib/telecallerLeads";

const PAGE_SIZE = 50;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** QA-02: a hand-edited URL value the API would answer with 422 (an unknown priority, a malformed id) is ignored, not sent -- otherwise
 *  the list could only ever say "Unable to load leads". An unknown stage is harmless (it just matches nothing). */
function validFilter(key: LeadListFilter, value: string): string {
  if (key === "priority") return PRIORITIES.some((p) => p.key === value) ? value : "";
  if (key === "product_id" || key === "campaign_id") return UUID.test(value) ? value : "";
  if (key === "follow_up") return FOLLOW_UP_FILTERS.some((f) => f.key === value) ? value : "";
  return value;
}

/** tel-008 (spec §3, D3): My Leads (and a manager's Leads). The API scopes, filters, searches and pages; the filters, search and page live
 *  in the URL, so refresh keeps the place and Back returns to the previous view (the admin lead panel's idiom). */
export default function TelecallerLeadTable({ basePath, showTelecaller = false }: { basePath: string; showTelecaller?: boolean }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const query = (params.get("q") ?? "").trim();
  const offset = pageOffset(params.get("offset") ?? undefined);
  const filters = Object.fromEntries(LEAD_LIST_FILTERS.map((key) => [key, validFilter(key, params.get(key) ?? "")])) as Record<LeadListFilter, string>;
  const request = new URLSearchParams(Object.entries(filters).filter(([, value]) => value));
  if (query) request.set("q", query);
  request.set("limit", String(PAGE_SIZE));
  request.set("offset", String(offset));
  const requestUrl = `${LEADS_URL}?${request}`;
  const filtered = !!query || Object.values(filters).some(Boolean);

  const [data, setData] = useState<Page<TelecallerLead> | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [draft, setDraft] = useState(query);
  const [products, setProducts] = useState<Product[]>([]);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  useEffect(() => setDraft(query), [query]);

  useEffect(() => {
    const controller = new AbortController();
    setLoadFailed(false);
    getPage<TelecallerLead>(requestUrl, controller.signal).then(setData).catch(() => controller.signal.aborted || setLoadFailed(true));
    return () => controller.abort();
  }, [requestUrl, version]);

  useEffect(() => {
    // A picker that fails to load leaves just "All", so the other filters keep working.
    const controller = new AbortController();
    activeProducts(controller.signal).then(setProducts).catch(() => undefined);
    activeCampaigns(controller.signal).then(setCampaigns).catch(() => undefined);
    return () => controller.abort();
  }, []);

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

  const select = (key: LeadListFilter, label: string, all: string, options: React.ReactNode) => (
    <div className="field" style={{ flex: "1 1 10rem" }}>
      <label htmlFor={`tel-lead-${key}`}>{label}</label>
      <select id={`tel-lead-${key}`} value={filters[key]} onChange={(event) => go({ [key]: event.target.value })}>
        <option value="">{all}</option>
        {options}
      </select>
    </div>
  );

  return (
    <div className="action-card" aria-busy={data === null && !loadFailed}>
      <form role="search" onSubmit={(event) => { event.preventDefault(); go({ q: draft.trim() }); }}
        style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
        <div className="field" style={{ flex: "1 1 16rem", minWidth: 0, marginBottom: 0 }}>
          <label htmlFor="tel-lead-search">Search leads</label>
          <span id="tel-lead-search-hint" className="muted" style={{ fontSize: 13 }}>Lead ID, name, phone, WhatsApp or email</span>
          <input id="tel-lead-search" className="search" type="search" aria-describedby="tel-lead-search-hint" value={draft} maxLength={200}
            onChange={(event) => setDraft(event.target.value)} />
        </div>
        <button type="submit" className="btn secondary small">Search</button>
        {query && <button type="button" className="btn secondary small" onClick={() => go({ q: "" })}>Clear search</button>}
      </form>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginTop: 8 }}>
        {select("status", "Stage", "All stages", STAGES.map(([key, label]) => <option key={key} value={key}>{label}</option>))}
        {select("priority", "Priority", "All priorities", PRIORITIES.map((p) => <option key={p.key} value={p.key}>{p.label}</option>))}
        {select("product_id", "Product", "All products", <ProductOptions products={products} />)}
        {select("campaign_id", "Campaign", "All campaigns", campaigns.map((c) => <option key={c.id} value={c.id}>{c.name}</option>))}
        {select("follow_up", "Due follow-up", "Any", FOLLOW_UP_FILTERS.map((f) => <option key={f.key} value={f.key}>{f.label}</option>))}
      </div>
      {loadFailed ? (
        <div style={{ marginTop: 12 }}>
          <p className="form-error" role="alert">Unable to load leads.</p>
          <button type="button" className="btn secondary small" onClick={() => setVersion((v) => v + 1)}>Retry</button>
        </div>
      ) : data === null ? (
        <p className="muted" role="status" style={{ marginTop: 12 }}>Loading leads…</p>
      ) : data.items.length === 0 ? (
        <p className="muted" role="status" style={{ marginTop: 12 }}>
          {filtered ? "No leads match these filters." : showTelecaller ? "No leads in your team yet." : "No leads are assigned to you yet."}
        </p>
      ) : (
        <>
          <div className="table-scroll" style={{ marginTop: 12 }}>
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Name</th>
                  <th scope="col">Lead ID</th>
                  <th scope="col">Mobile</th>
                  <th scope="col">Interest</th>
                  <th scope="col">Stage</th>
                  <th scope="col">Priority</th>
                  {showTelecaller && <th scope="col">Telecaller</th>}
                  <th scope="col">Lead date</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((lead) => (
                  <tr key={lead.id}>
                    <th scope="row"><Link href={`${basePath}/${encodeURIComponent(lead.id)}`} style={LINK_STYLE}>{lead.name}</Link></th>
                    <td style={{ whiteSpace: "nowrap" }}>{lead.lead_code}</td>
                    <td style={{ whiteSpace: "nowrap" }}>{lead.phone ?? <span className="muted">—</span>}</td>
                    <td>{lead.product?.name ?? lead.subject}</td>
                    <td>
                      {lead.status_label}
                      {lead.counselor && <div className="muted" style={{ fontSize: 13 }}>With counselor</div>} {/* QA-01: handed over (D1) */}
                    </td>
                    <td>{PRIORITY_LABEL[lead.priority] ?? lead.priority}</td>
                    {showTelecaller && <td>{lead.telecaller ? lead.telecaller.full_name : <span className="muted">Unassigned</span>}</td>}
                    <td style={{ whiteSpace: "nowrap" }}>{formatDate(lead.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.total > PAGE_SIZE && (
            <nav aria-label="Lead pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
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
