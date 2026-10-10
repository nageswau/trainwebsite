"use client";

import LeadTimeline from "@/components/LeadTimeline";
import type { Page } from "@/lib/apiErrors";
import { activityActor, activityEntry, type ActivityRow, universityTimelineUrl } from "@/lib/universityActivity";

/** upc-013 (DEC-SCOPE-165 D5, TL9/TL10): the university's communication history (§12) in the shared `.jtl` list. A client component, so
 *  it can hand the list its mappers. Every write on the page refreshes it, and a new first page (another total or newest row) remounts
 *  the list, so the entry just recorded shows without a reload. `initial` null: the server's read failed (Retry). */
export default function UniversityActivity({ universityId, initial }: { universityId: string; initial: Page<ActivityRow> | null }) {
  const first = initial ? `${initial.total}|${initial.items[0]?.kind ?? ""}|${initial.items[0]?.event ?? ""}|${initial.items[0]?.id ?? ""}` : "failed";
  return (
    <LeadTimeline<ActivityRow> key={first} url={universityTimelineUrl(universityId)} initial={initial} version={0} label="Communication history"
      entryOf={activityEntry} actorOf={activityActor} />
  );
}
