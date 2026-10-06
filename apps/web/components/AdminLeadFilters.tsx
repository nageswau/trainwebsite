"use client";

import { useEffect, useState } from "react";

import ProductOptions from "@/components/TelecallerProductOptions";
import { SOURCES, SOURCE_LABEL, activeCampaigns, activeProducts, type Campaign, type Product } from "@/lib/telecallerCatalogue";

export const LEAD_FILTERS = ["status", "source", "product_id", "campaign_id", "telecaller_user_id", "bdm_organization_id"] as const;
export type LeadFilter = (typeof LEAD_FILTERS)[number];
export type Organization = { id: string; code: string; name: string };
type Telecaller = { id: string; name: string };

// The legacy statuses until tel-004's pipeline stages replace them (spec L5).
export const STATUS_OPTIONS = ["new", "contacted", "qualified", "converted", "lost"];

/** tel-003 (spec §5): the admin lead list's search and filters. Values come from and go to the URL (the panel owns that); the option
 *  lists are the catalogue (tel-002), the division's telecallers (/admin/users is already division-scoped) and the organizations the
 *  panel has seen. A list that fails to load leaves just "All", so the other filters keep working. */
export default function AdminLeadFilters({ values, query, organizations, onChange, onSearch }: {
  values: Record<LeadFilter, string>;
  query: string;
  organizations: Organization[];
  onChange: (key: LeadFilter, value: string) => void;
  onSearch: (text: string) => void;
}) {
  const [draft, setDraft] = useState(query);
  const [products, setProducts] = useState<Product[]>([]);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [telecallers, setTelecallers] = useState<Telecaller[]>([]);
  useEffect(() => setDraft(query), [query]);
  useEffect(() => {
    const controller = new AbortController();
    activeProducts(controller.signal).then(setProducts).catch(() => undefined);
    activeCampaigns(controller.signal).then(setCampaigns).catch(() => undefined);
    fetch("/api/v1/admin/users?role=telecaller", { signal: controller.signal })
      .then((res) => (res.ok ? res.json() : []))
      .then((body: unknown) => Array.isArray(body) && setTelecallers(body.map((u: Telecaller) => ({ id: u.id, name: u.name }))))
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  const select = (key: LeadFilter, label: string, all: string, options: React.ReactNode) => (
    <div className="field" style={{ flex: "1 1 11rem" }}>
      <label htmlFor={`admin-lead-${key}`}>{label}</label>
      <select id={`admin-lead-${key}`} value={values[key]} onChange={(event) => onChange(key, event.target.value)}>
        <option value="">{all}</option>
        {options}
      </select>
    </div>
  );

  return (
    <>
      <form role="search" onSubmit={(event) => { event.preventDefault(); onSearch(draft.trim()); }}
        style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", marginTop: 8 }}>
        <input type="search" aria-label="Search leads" placeholder="Lead ID, name, email, phone or subject" value={draft} maxLength={200}
          onChange={(event) => setDraft(event.target.value)} style={{ flex: "1 1 220px", minWidth: 0 }} />
        <button type="submit" className="btn secondary small">Search</button>
        {query && <button type="button" className="btn secondary small" onClick={() => onSearch("")}>Clear search</button>}
      </form>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginTop: 8 }}>
        {select("status", "Stage", "All stages", STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>))}
        {select("source", "Source", "All sources", SOURCES.map((s) => <option key={s} value={s}>{SOURCE_LABEL[s]}</option>))}
        {select("product_id", "Product", "All products", <ProductOptions products={products} />)}
        {select("campaign_id", "Campaign", "All campaigns", campaigns.map((c) => <option key={c.id} value={c.id}>{c.name}</option>))}
        {select("telecaller_user_id", "Telecaller", "All telecallers", telecallers.map((t) => <option key={t.id} value={t.id}>{t.name}</option>))}
        {select("bdm_organization_id", "Organization", "All organizations", <>
          {organizations.map((o) => <option key={o.id} value={o.id}>{o.code} · {o.name}</option>)}
          {/* a filter from the URL whose organization has no lead on screen (an empty result) still shows as chosen */}
          {values.bdm_organization_id && !organizations.some((o) => o.id === values.bdm_organization_id) &&
            <option value={values.bdm_organization_id}>Selected organization</option>}
        </>)}
      </div>
    </>
  );
}
