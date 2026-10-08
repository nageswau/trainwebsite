// rec-025 (DEC-SCOPE-132): recruiter calls on a company contact or a candidate -- types, the CA1 outcomes (mirroring
// services/recruiter_calls.py), the endpoints and the `tel:` link. The API decides scope, every rule and `can_change` (the caller, on the
// call's IST day, while they can still write to the party); the UI only offers what it allows.
import { COMPANIES_URL } from "@/lib/recruiterCompanies";

export const OUTCOMES = [
  { key: "connected", label: "Connected", connected: true },
  { key: "call_back_requested", label: "Call back requested", connected: true },
  { key: "busy", label: "Busy", connected: false },
  { key: "no_answer", label: "No answer", connected: false },
  { key: "switched_off", label: "Switched off", connected: false },
  { key: "wrong_number", label: "Wrong number", connected: false },
] as const;
export const DIRECTIONS = [{ key: "outgoing", label: "Outgoing" }, { key: "incoming", label: "Incoming" }] as const;
export const NOTES_MAX = 2000;
export const LIST_LIMIT = 50;

type PersonRef = { id: string; full_name: string };
export type RecCall = {
  id: string; kind: "contact" | "candidate"; company_id: string | null; contact: { id: string; name: string } | null;
  candidate: { id: string; name: string; code: string } | null; occurred_at: string; duration_seconds: number | null;
  direction: "outgoing" | "incoming"; outcome: string; outcome_label: string; connected: boolean; notes: string | null; caller: PersonRef;
  created_at: string; can_change: boolean;
};
export type LogCallResult = { call: RecCall; follow_up_id: string | null };
/** Who a call is with: a contact of the company (picked in the form) or one candidate. */
export type CallParty = { kind: "contact"; companyId: string } | { kind: "candidate"; candidateId: string };

export const CALLS_URL = "/api/v1/recruiter/calls";
export const callUrl = (id: string) => `${CALLS_URL}/${encodeURIComponent(id)}`;
export function partyCallsUrl(party: CallParty): string {
  const base = party.kind === "contact" ? `${COMPANIES_URL}/${encodeURIComponent(party.companyId)}` : `/api/v1/recruiter/candidates/${encodeURIComponent(party.candidateId)}`;
  return `${base}/calls?limit=${LIST_LIMIT}`;
}

/** A `tel:` href from a typed phone: digits and a leading +, or null when there is no number to dial. */
export function telHref(phone: string | null | undefined): string | null {
  const trimmed = (phone ?? "").trim();
  const digits = trimmed.replace(/\D/g, "");
  if (digits.length < 4) return null;
  return `tel:${trimmed.startsWith("+") ? "+" : ""}${digits}`;
}

export function isRecCall(data: unknown): data is RecCall {
  const d = data as Partial<RecCall> | null;
  return !!d && typeof d.id === "string" && typeof d.occurred_at === "string" && typeof d.outcome === "string" && typeof d.can_change === "boolean";
}

export function isLogCallResult(data: unknown): data is LogCallResult {
  const d = data as Partial<LogCallResult> | null;
  return !!d && isRecCall(d.call) && "follow_up_id" in d;
}
