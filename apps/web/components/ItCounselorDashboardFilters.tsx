"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";

import type { ItCounselorDashboard, ItCounselorFilterKey } from "@/lib/types";

const KEYS: ItCounselorFilterKey[] = ["program", "batch", "stage", "from", "to", "owner"];
const FORM = { display: "flex", flexWrap: "wrap", gap: 12, alignItems: "end", marginBottom: 12 } as const;

/** itc-030 (DEC-SCOPE-367 AC2): course, batch, status, date range and -- the IT Admin only (owners offered) -- owner. The values live in
 *  the address, so a filtered dashboard survives a reload and Back; an empty field is left out, and the server refuses a bad value. */
export default function ItCounselorDashboardFilters({ filters, options, error }: { filters: ItCounselorDashboard["filters"]; options: ItCounselorDashboard["options"]; error?: string | null }) {
  const router = useRouter();
  const pathname = usePathname();
  const [program, setProgram] = useState(filters.program ?? "");
  const batches = program ? options.batches.filter((b) => b.program === program) : options.batches;

  function apply(form: HTMLFormElement) {
    const data = new FormData(form);
    const query = new URLSearchParams(KEYS.flatMap((key) => { const v = String(data.get(key) ?? ""); return v ? [[key, v]] : []; }));
    const qs = query.toString();
    router.push(qs ? `${pathname}?${qs}` : pathname);
  }

  return (
    <form className="form filter-bar" aria-label="Filter the dashboard" style={FORM} onSubmit={(event) => { event.preventDefault(); apply(event.currentTarget); }}>
      <div className="field">
        <label htmlFor="itc-dash-program">Course</label>
        <select id="itc-dash-program" name="program" value={program} onChange={(event) => setProgram(event.target.value)}>
          <option value="">All courses</option>
          {options.programs.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </div>
      <div className="field">
        <label htmlFor="itc-dash-batch">Batch</label>
        {/* re-keyed by course, so a batch of another course never stays picked */}
        <select key={program} id="itc-dash-batch" name="batch" defaultValue={batches.some((b) => b.value === filters.batch) ? filters.batch ?? "" : ""}>
          <option value="">All batches</option>
          {batches.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </div>
      <div className="field">
        <label htmlFor="itc-dash-stage">Status</label>
        <select id="itc-dash-stage" name="stage" defaultValue={filters.stage ?? ""}>
          <option value="">All statuses</option>
          {options.stages.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </div>
      <div className="field">
        <label htmlFor="itc-dash-from">From</label>
        <input id="itc-dash-from" name="from" type="date" defaultValue={filters.from ?? ""} />
      </div>
      <div className="field">
        <label htmlFor="itc-dash-to">To</label>
        <input id="itc-dash-to" name="to" type="date" defaultValue={filters.to ?? ""} />
      </div>
      {options.owners.length > 0 && (
        <div className="field">
          <label htmlFor="itc-dash-owner">Owner</label>
          <select id="itc-dash-owner" name="owner" defaultValue={filters.owner ?? ""}>
            <option value="">All counselors</option>
            {options.owners.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>
      )}
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <button className="btn small" type="submit">Apply filters</button>
        <Link href={pathname}>Clear filters</Link>
      </div>
      {error && <p className="form-error" role="alert" style={{ margin: 0, flexBasis: "100%" }}>{error}</p>}
    </form>
  );
}
