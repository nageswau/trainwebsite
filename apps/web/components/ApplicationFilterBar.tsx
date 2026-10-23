"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { APPLICATION_FILTER_KEYS, type ApplicationFilterKey, type ApplicationFilterState, type FilterOption } from "@/lib/types";

type Values = Partial<Record<ApplicationFilterKey, string | null>>;

// AGN-023 (DEC-SCOPE-090 H11): Agency (Admin and counselor) and Counsellor (Admin only) filters. The values live in the URL, so a
// filtered list survives a reload and can be shared; the server applies them (before its row cap) and refuses a bad value.
// ccrm-012 (DEC-SCOPE-246 QS6): Country, University, Intake, Stage, Sub-status and the created-date range, under the same rules.
export default function ApplicationFilterBar({ filters, error }: { filters: ApplicationFilterState; error?: string | null }) {
  const router = useRouter();
  const pathname = usePathname();
  const current: Values = Object.fromEntries(APPLICATION_FILTER_KEYS.map((key) => [key, filters[key] ?? null]));

  function go(change: Values) {
    const next = { ...current, ...change };
    // A sub-status belongs to one stage: changing the stage drops a sub-status that no longer fits.
    if ("stage" in change && next.sub_status && next.stage && filters.sub_statuses?.find((o) => o.value === next.sub_status)?.stage !== next.stage) next.sub_status = null;
    const params = new URLSearchParams();
    for (const key of APPLICATION_FILTER_KEYS) if (next[key]) params.set(key, next[key] as string);
    const query = params.toString();
    router.push(query ? `${pathname}?${query}` : pathname);
  }

  function select(key: ApplicationFilterKey, label: string, options: FilterOption[] | undefined, extra: FilterOption[] = []) {
    if (!options) return null;
    return (
      <div className="field">
        <label htmlFor={`filter-${key}`}>{label}</label>
        <select id={`filter-${key}`} value={current[key] ?? ""} onChange={(event) => go({ [key]: event.target.value || null })}>
          <option value="">All</option>
          {[...extra, ...options].map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
      </div>
    );
  }

  const subStatuses = filters.sub_statuses?.filter((o) => !current.stage || o.stage === current.stage);
  // A refused filter falls back to the unfiltered list (nothing applied), but the URL still carries the bad value, so keep the way out.
  const applied = APPLICATION_FILTER_KEYS.some((key) => current[key]) || Boolean(error);
  return (
    <form className="form filter-bar" aria-label="Filter applications" onSubmit={(event) => event.preventDefault()} style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "end", marginBottom: 12 }}>
      {select("agency", "Agency", filters.agencies, [{ value: "any", label: "Any agency" }, { value: "none", label: "Not from an agency" }])}
      {select("counselor", "Counsellor", filters.counselors, [{ value: "none", label: "Not assigned" }])}
      {select("country", "Destination", filters.countries)}
      {select("university", "University", filters.universities)}
      {select("intake", "Intake", filters.intakes)}
      {select("stage", "Stage", filters.stages)}
      {select("sub_status", "Sub-status", subStatuses)}
      {filters.stages && (
        <>
          <div className="field">
            <label htmlFor="filter-from">Created from</label>
            <input id="filter-from" type="date" value={current.from ?? ""} max={current.to ?? undefined} onChange={(event) => go({ from: event.target.value || null })} />
          </div>
          <div className="field">
            <label htmlFor="filter-to">Created to</label>
            <input id="filter-to" type="date" value={current.to ?? ""} min={current.from ?? undefined} onChange={(event) => go({ to: event.target.value || null })} />
          </div>
        </>
      )}
      {applied && <Link href={pathname}>Clear filters</Link>}
      {error && <p className="form-error" role="alert">{error} -- showing all applications.</p>}
    </form>
  );
}
