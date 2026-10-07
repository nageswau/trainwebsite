// tel-010 (DEC-SCOPE-096): calls on a lead -- types, the EVID-019 §5 outcomes (mirroring services/lead_calls.py) and the endpoints. The
// API decides scope, every rule and `can_change` (the caller, on the call's IST day, lead not handed over); the UI only offers what it allows.
import { leadUrl, type PersonRef } from "@/lib/telecallerLeads";

type Outcome = { key: string; label: string; connected: boolean; closes?: string; followUp?: boolean };
export const OUTCOMES: readonly Outcome[] = [
  { key: "interested", label: "Connected – Interested", connected: true },
  { key: "need_information", label: "Connected – Need Information", connected: true },
  { key: "follow_up_required", label: "Connected – Follow-up Required", connected: true, followUp: true },
  { key: "appointment_fixed", label: "Connected – Appointment Fixed", connected: true },
  { key: "not_interested", label: "Not Interested", connected: true, closes: "Not Interested" },
  { key: "wrong_number", label: "Wrong Number", connected: false, closes: "Wrong Number" },
  { key: "busy", label: "Busy", connected: false },
  { key: "no_answer", label: "No Answer", connected: false },
  { key: "switched_off", label: "Switched Off", connected: false },
  { key: "call_back_requested", label: "Call Back Requested", connected: true, followUp: true },
  { key: "already_joined", label: "Already Joined Elsewhere", connected: true, closes: "Lost" },
  { key: "duplicate_lead", label: "Duplicate Lead", connected: true },
  { key: "not_eligible", label: "Not Eligible", connected: true, closes: "Not Eligible" },
];
const BY_KEY = new Map(OUTCOMES.map((o) => [o.key, o]));
export const outcomeLabel = (key: string) => BY_KEY.get(key)?.label ?? key;
/** D3: the closed stage's label an outcome moves the lead to, or null. */
export const closesAs = (key: string) => BY_KEY.get(key)?.closes ?? null;
/** D4: the outcomes that need a next follow-up. */
export const needsFollowUp = (key: string) => !!BY_KEY.get(key)?.followUp;
export const CALL_TYPES = [{ key: "outgoing", label: "Outgoing" }, { key: "incoming", label: "Incoming" }] as const; // CL1
export const REMARKS_MAX = 2000;
export const MAX_SECONDS = 14400; // D7

export type LeadCall = {
  id: string; lead_id: string; occurred_at: string; duration_seconds: number; call_type: "outgoing" | "incoming"; outcome: string;
  outcome_label: string; connected: boolean; remarks: string | null; caller: PersonRef; created_at: string; can_change: boolean;
};
export type LogCallResult = { call: LeadCall; lead: { id: string; status: string; status_label: string }; follow_up_id: string | null };

export const LIST_LIMIT = 50;
export const leadCallsUrl = (leadId: string) => leadUrl(leadId, `/calls?limit=${LIST_LIMIT}`);
export const createCallUrl = (leadId: string) => leadUrl(leadId, "/calls");
export const callUrl = (id: string) => `/api/v1/telecaller/calls/${encodeURIComponent(id)}`;

export function isLeadCall(data: unknown): data is LeadCall {
  const d = data as Partial<LeadCall> | null;
  return !!d && typeof d.id === "string" && typeof d.occurred_at === "string" && typeof d.outcome === "string" && typeof d.can_change === "boolean";
}

export function isLogCallResult(data: unknown): data is LogCallResult {
  const d = data as Partial<LogCallResult> | null;
  return !!d && isLeadCall(d.call) && !!d.lead && typeof d.lead.status === "string";
}

export function formatDuration(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  if (!minutes) return `${rest} s`;
  return rest ? `${minutes} min ${rest} s` : `${minutes} min`;
}

/** The form's minutes + seconds as whole seconds; null when either is not a whole number in range (blank counts as 0). */
export function toSeconds(minutes: string, seconds: string): number | null {
  const parts = [minutes.trim() || "0", seconds.trim() || "0"];
  if (!parts.every((p) => /^\d+$/.test(p))) return null;
  const [m, s] = parts.map(Number);
  if (s > 59) return null;
  const total = m * 60 + s;
  return total <= MAX_SECONDS ? total : null;
}
