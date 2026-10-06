// tel-008 (DEC-SCOPE-084): the telecaller lead workspace -- types, labels and endpoints shared by My Leads and the lead detail. Labels
// are display only; the API decides scope, editability (`read_only`) and every rule.
import { sendJson, type SendOutcome } from "@/lib/apiErrors";

export type Priority = "hot" | "warm" | "cold";
export type PersonRef = { id: string; full_name: string };
export type TelecallerLead = {
  id: string; lead_code: string; name: string; email: string | null; phone: string | null; whatsapp_number: string | null; city: string | null;
  state: string | null; qualification: string | null; passing_year: number | null; institution: string | null; division: string; subject: string;
  status: string; status_label: string; source: string; priority: Priority; created_at: string; stage_changed_at: string;
  product: { id: string; name: string } | null; campaign: { id: string; name: string } | null; telecaller: PersonRef | null; counselor: PersonRef | null;
  read_only: boolean;
};
export type TelecallerLeadDetail = TelecallerLead & { message: string };
export type TimelineRow = {
  id: string; kind: "stage" | "priority" | "enquiry"; at: string; actor: PersonRef | null; from_value: string; from_label: string; to_value: string;
  to_label: string; reason: string | null;
};

/** tel-005 (R2): one lead of the §18 duplicate panel -- never its phone, email or messages. */
export type DuplicateMatch = {
  id: string; lead_code: string; name: string; status: string; status_label: string; telecaller: PersonRef | null; counselor: PersonRef | null;
  last_contact_at: string | null; matched_on: ("phone" | "email")[]; enquiries: { subject: string; source: string; at: string }[]; in_scope: boolean;
};

export const LEADS_URL = "/api/v1/telecaller/leads";
export const DUPLICATE_CHECK_URL = `${LEADS_URL}/duplicate-check`;
export const leadUrl = (id: string, suffix = "") => `${LEADS_URL}/${encodeURIComponent(id)}${suffix}`;
export const TIMELINE_LIMIT = 50;
export const LEAD_LIST_FILTERS = ["status", "priority", "product_id", "campaign_id", "follow_up"] as const; // tel-011 F9: follow_up
export type LeadListFilter = (typeof LEAD_LIST_FILTERS)[number];
export const FOLLOW_UP_FILTERS = [{ key: "today", label: "Due today" }, { key: "overdue", label: "Overdue" }] as const;

// EVID-019 §8 (L316-L328): three levels, with the source's own help text.
export const PRIORITIES: { key: Priority; label: string; help: string }[] = [
  { key: "hot", label: "Hot", help: "Ready to join / immediate requirement." },
  { key: "warm", label: "Warm", help: "Interested but needs follow-up." },
  { key: "cold", label: "Cold", help: "Long-term / low interest." },
];
export const PRIORITY_LABEL: Record<string, string> = Object.fromEntries(PRIORITIES.map((p) => [p.key, p.label]));

/** A `tel:` link (T7): digits and one leading + only, so nothing else ever reaches the href; null when there is no usable number. */
export function telHref(phone: string | null): string | null {
  const compact = (phone ?? "").trim().replace(/[^\d+]/g, "");
  const digits = compact.replace(/\+/g, "");
  return digits.length >= 6 ? `tel:${compact.startsWith("+") ? "+" : ""}${digits}` : null;
}

/** tel-004's telecaller stage route ({to_stage, reason}); LeadStageControl calls it on the lead detail. */
export const moveStage = (id: string, target: string, reason: string): Promise<SendOutcome> =>
  sendJson(leadUrl(id, "/stage"), "POST", reason ? { to_stage: target, reason } : { to_stage: target });
