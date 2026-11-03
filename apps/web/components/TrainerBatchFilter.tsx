"use client";

import { usePathname, useRouter } from "next/navigation";

import type { BatchFilter } from "@/lib/types";

/** itc-024 (DEC-SCOPE-355 W5): narrows the trainer dashboard to one of the trainer's own batches. The value lives in the address
 *  (`?batch=`), so a filtered dashboard survives a reload; the server applies it and refuses a batch that is not the trainer's. */
export default function TrainerBatchFilter({ filter, error }: { filter: BatchFilter; error?: string | null }) {
  const router = useRouter();
  const pathname = usePathname();
  return (
    <form className="form filter-bar" aria-label="Filter the dashboard" onSubmit={(event) => event.preventDefault()} style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "end", marginBottom: 12 }}>
      <div className="field">
        <label htmlFor="trainer-batch-filter">Batch</label>
        <select id="trainer-batch-filter" value={filter.value ?? ""} onChange={(event) => router.push(event.target.value ? `${pathname}?batch=${encodeURIComponent(event.target.value)}` : pathname)}>
          <option value="">All batches</option>
          {filter.options.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
      </div>
      {error && <p className="form-error" role="alert" style={{ margin: 0, flexBasis: "100%" }}>{error}</p>}
    </form>
  );
}
