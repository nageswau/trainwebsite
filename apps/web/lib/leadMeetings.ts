// ccrm-004 (DEC-SCOPE-259 LG3): meetings the counselor records on a lead handed to them -- types, the modes (the appointment modes) and
// the endpoint. The API decides scope and every rule (no future time, up to 7 days back, closed lead 409).
import { counselorLeadUrl } from "@/lib/leadHandover";
import type { PersonRef } from "@/lib/telecallerLeads";

export const MEETING_MODES = ["In person", "Online", "Phone"] as const;
export const NOTES_MAX = 2000;
export const LIST_LIMIT = 50;
export type LeadMeeting = { id: string; occurred_at: string; mode: string; notes: string; author: PersonRef; created_at: string };

export const meetingsUrl = (leadId: string, list = false) => counselorLeadUrl(leadId, list ? `/meetings?limit=${LIST_LIMIT}` : "/meetings");

export function isLeadMeeting(data: unknown): data is LeadMeeting {
  const d = data as Partial<LeadMeeting> | null;
  return !!d && typeof d.id === "string" && typeof d.occurred_at === "string" && typeof d.notes === "string";
}
