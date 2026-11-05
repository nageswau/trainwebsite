"use client";
import { useEffect, useState } from "react";

import LeadTimeline from "@/components/LeadTimeline";
import LocalTime from "@/components/LocalTime";
import type { Page } from "@/lib/apiErrors";
import { contactFollowUpsUrl, contactTimelineUrl } from "@/lib/recruiterContacts";
import { reasonLabel, type RecFollowUp } from "@/lib/recruiterFollowUps";
import { timelineActor, timelineEntry, type RecTimelineRow } from "@/lib/recruiterTimeline";
import { getPage } from "@/lib/telecallerCatalogue";

const FOLLOW_UP_STATE: Record<RecFollowUp["status"], string> = { open: "Open", done: "Done", cancelled: "Cancelled" };

/** pob-005 (DEC-SCOPE-410 D10/D11): one contact's own activity -- their follow-ups and their timeline (calls, messages and replies,
 *  meetings, shares and status changes). Read only; the API scopes both lists to the company and checks the contact belongs to it. */
export default function RecruiterContactActivity({ companyId, contactId, name, version }: { companyId: string; contactId: string; name: string; version: number }) {
  const [followUps, setFollowUps] = useState<Page<RecFollowUp> | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    getPage<RecFollowUp>(contactFollowUpsUrl(companyId, contactId), controller.signal).then(setFollowUps).catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [companyId, contactId, version]);

  return (
    <div style={{ display: "grid", gap: 8, marginTop: 8 }}>
      <h5 style={{ margin: 0 }}>Follow-ups with {name}</h5>
      {failed ? (
        <p className="form-error" role="alert" style={{ fontSize: 13, margin: 0 }}>The follow-ups could not be loaded.</p>
      ) : followUps === null ? (
        <p className="muted" style={{ fontSize: 13, margin: 0 }}>Loading follow-ups…</p>
      ) : followUps.items.length === 0 ? (
        <p className="muted" style={{ fontSize: 13, margin: 0 }}>No follow-ups about this contact.</p>
      ) : (
        <ul aria-label={`Follow-ups with ${name}`} style={{ margin: 0, paddingLeft: 18, fontSize: 14 }}>
          {followUps.items.map((fu) => (
            <li key={fu.id}>
              {reasonLabel(fu.reason)} · due <LocalTime value={fu.due_at} time /> · {fu.status === "open" && fu.overdue ? "Overdue" : FOLLOW_UP_STATE[fu.status]}
            </li>
          ))}
        </ul>
      )}
      <h5 style={{ margin: 0 }}>Timeline with {name}</h5>
      <LeadTimeline<RecTimelineRow> url={contactTimelineUrl(companyId, contactId)} version={version} label={`Timeline with ${name}`} entryOf={timelineEntry} actorOf={timelineActor} />
    </div>
  );
}
