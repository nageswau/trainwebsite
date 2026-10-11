"use client";

import LeadTimeline from "@/components/LeadTimeline";
import { candidateTimelineUrl, companyTimelineUrl, timelineActor, timelineEntry, type RecTimelineRow } from "@/lib/recruiterTimeline";

/** rec-027 (spec TL10): a company's or a candidate's timeline in the shared `.jtl` list (loading, empty, Retry, "Show older entries").
 *  A `version` change re-reads the first page -- the company page bumps it after each write. */
export default function RecruiterTimeline({ party, version = 0 }: { party: { kind: "company" | "candidate"; id: string }; version?: number }) {
  const headingId = `${party.kind}-${party.id}-timeline`;
  const url = party.kind === "company" ? companyTimelineUrl(party.id) : candidateTimelineUrl(party.id);
  return (
    <section className="action-card wide" aria-labelledby={headingId}>
      <h3 id={headingId}>Timeline</h3>
      <LeadTimeline<RecTimelineRow> url={url} version={version} label={party.kind === "company" ? "Company timeline" : "Candidate timeline"}
        entryOf={timelineEntry} actorOf={timelineActor} />
    </section>
  );
}
