// rec-022 (DEC-SCOPE-155): offers -- types, the EVID-018 §16 status labels, the endpoints and the history wording. The API decides scope,
// every rule (Selected only, the moves, the dates, the letter type) and what the viewer may do (`can_create`, `allowed_statuses`,
// `can_edit`, `can_upload`); the UI only offers what it allows.
// rec-023 (DEC-SCOPE-158): the offer's §17 joining, its proof and the joinings list.
import { isPage, type Page } from "@/lib/apiErrors";

/** EVID-018 §16 (L700), in source order and wording; the history names statuses by key. */
export const OFFER_STATUS_LABELS: Record<string, string> = {
  offer_pending: "Offer Pending", offer_received: "Offer Received", accepted: "Accepted", declined: "Declined",
};
/** OF4: an offer starts as one of these. */
export const START_STATUSES = ["offer_pending", "offer_received"] as const;
/** The four revisable fields and their labels (history rows name changed fields, never values). */
export const FIELD_LABELS: Record<string, string> = {
  position: "Position", compensation: "Salary", currency: "Currency", offered_on: "Offer date", joining_date: "Joining date",
};
export const NOTE_MAX = 500;
export const LETTER_ACCEPT = ".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png";
export const LETTER_MAX_BYTES = 20 * 1024 * 1024;

/** EVID-018 §17 (L720-L728). */
export const JOINING_STATUS_LABELS: Record<string, string> = { pending: "Pending", joined: "Joined", did_not_join: "Did Not Join" };
/** The joining's details as the history names them (field names, never values). */
export const JOINING_FIELD_LABELS: Record<string, string> = {
  expected_joining_date: "Expected joining date", actual_joining_date: "Actual joining date", joining_location: "Joining location",
  reporting_manager: "Reporting manager", confirmed_by: "Confirmed by", confirmed_on: "Confirmation date", reason: "Reason",
};

type PersonRef = { id: string; full_name: string };
export type Joining = {
  status: string; status_label: string; expected_joining_date: string | null; actual_joining_date: string | null; location: string | null;
  reporting_manager: string | null; confirmed_by: string | null; confirmed_on: string | null; reason: string | null;
  proof: { name: string | null; content_type: string; uploaded_at: string } | null; overdue: boolean; allowed_statuses: { key: string; label: string }[];
  can_edit: boolean; can_upload_proof: boolean;
};
export type OfferEvent = {
  event: "created" | "status" | "revised" | "letter" | "joining" | "joined" | "did_not_join" | "proof"; from_status: string | null; to_status: string | null; fields: string[] | null;
  note: string | null; actor: PersonRef | null; created_at: string;
};
export type RecOffer = {
  id: string; status: string; status_label: string; position: string | null; compensation: string | number | null; currency: string;
  offered_on: string; joining_date: string | null; letter: { name: string | null; content_type: string; uploaded_at: string } | null;
  letter_url: string | null; application: { id: string; status: string; status_label: string }; candidate: { id: string; code: string; name: string };
  requirement: { id: string; code: string; title: string }; company: { id: string; name: string }; history: OfferEvent[];
  allowed_statuses: { key: string; label: string }[]; can_edit: boolean; can_upload: boolean; joining: Joining | null;
};
export type JoiningItem = {
  id: string; position: string | null; offered_on: string; application: { id: string; status: string; status_label: string };
  candidate: { id: string; code: string; name: string }; requirement: { id: string; code: string; title: string }; company: { id: string; name: string };
  joining: Joining;
};
export type JoiningView = "due" | "joined" | "did_not_join";
export const JOINING_TABS: [JoiningView, string][] = [["due", "Joining due"], ["joined", "Joined"], ["did_not_join", "Did not join"]];
export type JoiningListPage = Page<JoiningItem> & { counts: Record<JoiningView, number> };
export type ApplicationOffer = { offer: RecOffer | null; can_create: boolean; suggested_position?: string };
export type StudentOffer = {
  id: string; company: string; requirement: string; position: string | null; status: string; status_label: string; compensation: string | number | null;
  currency: string; offered_on: string; joining_date: string | null; has_letter: boolean; letter_url: string | null;
};

export const applicationOfferUrl = (applicationId: string) => `/api/v1/recruiter/applications/${encodeURIComponent(applicationId)}/offer`;
export const offerUrl = (id: string, action?: "status" | "letter" | "joining" | "joining/proof") => `/api/v1/recruiter/offers/${encodeURIComponent(id)}${action ? `/${action}` : ""}`;
export const STUDENT_OFFERS_URL = "/api/v1/workflows/it/student/offers";
export const studentLetterUrl = (id: string) => `${STUDENT_OFFERS_URL}/${encodeURIComponent(id)}/letter`;

export const JOININGS_URL = "/api/v1/recruiter/joinings";
export const JOININGS_LIMIT = 50;
export const joiningsUrl = (view: JoiningView, offset = 0) => `${JOININGS_URL}?${new URLSearchParams({ view, limit: String(JOININGS_LIMIT), offset: String(offset) })}`;
export const isJoiningView = (value: string | null): value is JoiningView => JOINING_TABS.some(([key]) => key === value);
export const isJoiningListPage = (data: unknown): data is JoiningListPage => isPage(data) && !!(data as { counts?: unknown }).counts;

export function isRecOffer(data: unknown): data is RecOffer {
  const d = data as Partial<RecOffer> | null;
  return !!d && typeof d.id === "string" && typeof d.status === "string" && Array.isArray(d.history) && Array.isArray(d.allowed_statuses);
}

/** Every write replies `{offer}`. */
export function offerOf(data: unknown): RecOffer | null {
  const inner = (data as { offer?: unknown } | null)?.offer;
  return isRecOffer(inner) ? inner : null;
}

export function isApplicationOffer(data: unknown): data is ApplicationOffer {
  const d = data as Partial<ApplicationOffer> | null;
  return !!d && typeof d.can_create === "boolean" && (d.offer === null || isRecOffer(d.offer));
}

export function isStudentOffers(data: unknown): data is { items: StudentOffer[] } {
  const items = (data as { items?: unknown } | null)?.items;
  return Array.isArray(items) && items.every((i) => typeof (i as StudentOffer)?.id === "string" && typeof (i as StudentOffer)?.status_label === "string");
}

/** "INR 6,00,000.00" (Indian grouping for INR); null when there is no salary. */
export function salaryText(amount: string | number | null, currency: string): string | null {
  if (amount === null || amount === "") return null;
  const value = Number(amount);
  if (!Number.isFinite(value)) return `${currency} ${amount}`;
  return `${currency} ${value.toLocaleString(currency === "INR" ? "en-IN" : "en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

const statusName = (key: string | null) => (key ? OFFER_STATUS_LABELS[key] ?? key : "?");

/** One history row in words; `at` is the caller's formatted time. */
export function offerEventText(h: OfferEvent, at: string): string {
  const by = h.actor ? ` by ${h.actor.full_name}` : "";
  const note = h.note ? ` — ${h.note}` : "";
  if (h.event === "created") return `Recorded as ${statusName(h.to_status)} ${at}${by}`;
  if (h.event === "revised") return `Revised (${(h.fields ?? []).map((f) => FIELD_LABELS[f] ?? f).join(", ")}) ${at}${by}`;
  if (h.event === "letter") return `Offer letter uploaded ${at}${by}`;
  if (h.event === "joining") return `Joining details updated (${(h.fields ?? []).map((f) => JOINING_FIELD_LABELS[f] ?? f).join(", ")}) ${at}${by}`;
  if (h.event === "joined") return `Joined ${at}${by}`;
  if (h.event === "did_not_join") return `Did Not Join ${at}${by}${note}`;
  if (h.event === "proof") return `Joining proof uploaded ${at}${by}`;
  return `${statusName(h.from_status)} → ${statusName(h.to_status)} ${at}${by}${note}`;
}
