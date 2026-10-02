"use client";

import { useState } from "react";

import { type AgentUniversity, optionLabel } from "@/lib/agentShortlist";
import type { University } from "@/lib/types";

// AGN-007: the shortlist form's university choice — catalogue and agency groups in one native select (spec §6 plan-time correction).
// Browser QA-06 (owner, 2026-10-02): a filter box narrows both groups by name, city or country; the current choice always stays listed.
const matches = (needle: string, ...parts: (string | null | undefined)[]) => !needle || parts.some((p) => p?.toLowerCase().includes(needle));

export default function AgentShortlistUniversityPicker({ idPrefix, catalogue, countries, agency, value, onChoose }: {
  idPrefix: string; catalogue: University[] | null; countries: Map<string, string> | null; agency: AgentUniversity[] | null; value: string; onChoose: (key: string) => void;
}) {
  const [filter, setFilter] = useState("");
  const ready = catalogue !== null;
  const needle = filter.trim().toLowerCase();
  const shownCatalogue = (catalogue ?? []).filter((u) => `c:${u.id}` === value || matches(needle, u.name, u.city, countries?.get(u.country_id)));
  const shownAgency = (agency ?? []).filter((u) => `a:${u.id}` === value || matches(needle, u.name, u.city, u.country));
  const total = (catalogue?.length ?? 0) + (agency?.length ?? 0);
  return (
    <>
      <div className="field">
        <label htmlFor={`${idPrefix}-filter`}>Filter universities</label>
        <input id={`${idPrefix}-filter`} type="search" value={filter} disabled={!ready} aria-describedby={`${idPrefix}-filter-count`} onChange={(e) => setFilter(e.target.value)} />
        <p className="muted" id={`${idPrefix}-filter-count`} aria-live="polite" style={{ fontSize: 12, margin: "4px 0 0" }}>
          {ready && needle ? `${shownCatalogue.length + shownAgency.length} of ${total} universities` : ""}
        </p>
      </div>
      <div className="field">
        <label htmlFor={`${idPrefix}-uni`}>University (required)</label>
        <select id={`${idPrefix}-uni`} value={value} disabled={!ready} aria-required="true" onChange={(e) => onChoose(e.target.value)}>
          <option value="">{ready ? "— Choose a university —" : "Loading universities…"}</option>
          {shownCatalogue.length > 0 && (
            <optgroup label="Catalogue">
              {shownCatalogue.map((u) => <option key={u.id} value={`c:${u.id}`}>{optionLabel(u.name, u.city)}</option>)}
            </optgroup>
          )}
          {shownAgency.length > 0 && (
            <optgroup label="Your agency">
              {shownAgency.map((u) => <option key={u.id} value={`a:${u.id}`}>{optionLabel(u.name, u.country)}</option>)}
            </optgroup>
          )}
        </select>
      </div>
    </>
  );
}
