"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import type { ApplicationFilterState } from "@/lib/types";

// AGN-023 (DEC-SCOPE-090 H11): Agency (Admin and counselor) and Counsellor (Admin only) filters. The values live in the URL, so a
// filtered list survives a reload and can be shared; the server applies them (before its row cap) and refuses a bad value.
export default function ApplicationFilterBar({ filters, error }: { filters: ApplicationFilterState; error?: string | null }) {
  const router = useRouter();
  const pathname = usePathname();

  function go(next: { agency: string | null; counselor: string | null }) {
    const params = new URLSearchParams();
    if (next.agency) params.set("agency", next.agency);
    if (next.counselor) params.set("counselor", next.counselor);
    const query = params.toString();
    router.push(query ? `${pathname}?${query}` : pathname);
  }

  // A refused filter falls back to the unfiltered list (nothing applied), but the URL still carries the bad value, so keep the way out.
  const applied = Boolean(filters.agency || filters.counselor || error);
  return (
    <form className="form filter-bar" aria-label="Filter applications" onSubmit={(event) => event.preventDefault()} style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "end", marginBottom: 12 }}>
      <div className="field">
        <label htmlFor="filter-agency">Agency</label>
        <select id="filter-agency" value={filters.agency ?? ""} onChange={(event) => go({ agency: event.target.value || null, counselor: filters.counselor })}>
          <option value="">All</option>
          <option value="any">Any agency</option>
          <option value="none">Not from an agency</option>
          {filters.agencies.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
      </div>
      {filters.counselors && (
        <div className="field">
          <label htmlFor="filter-counselor">Counsellor</label>
          <select id="filter-counselor" value={filters.counselor ?? ""} onChange={(event) => go({ agency: filters.agency, counselor: event.target.value || null })}>
            <option value="">All</option>
            <option value="none">Not assigned</option>
            {filters.counselors.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </div>
      )}
      {applied && <Link href={pathname}>Clear filters</Link>}
      {error && <p className="form-error" role="alert">{error} -- showing all applications.</p>}
    </form>
  );
}
