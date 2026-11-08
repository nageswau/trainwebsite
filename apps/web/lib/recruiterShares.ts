// rec-019 (DEC-SCOPE-160): profile sharing -- types, endpoints, guards and the requirement picker. The API decides every rule (the contact,
// the pool, the repeat warning, the channel's preconditions) and what a company may see (R8: never a phone, email or salary); the page
// only shows its answers. `can_respond` on each share says whether the viewer may record a response.
import { REQUIREMENTS_URL } from "@/lib/recruiterRequirements";

export type ShareChannel = "email" | "whatsapp" | "portal" | "other";
export type ShareRecipient = "client" | "vendor"; // pob-011 (DEC-SCOPE-427 V4)
export type ShareDetail = "named" | "anonymised" | "full"; // pob-011 V6: a client always gets the named summary
export type ShareResponse = "pending" | "interested" | "not_interested" | "interview_requested";
export type Person = { id: string; full_name: string };
// pob-021 (DEC-SCOPE-430): each shared candidate is a submission
export type SubmissionStatus = "submitted" | "client_reviewing" | "shortlisted" | "interview" | "rejected" | "on_hold" | "selected" | "withdrawn";
export type MatchBlock = {
  score: number; required_matched: string[]; required_missing: string[]; preferred_matched: string[]; preferred_missing: string[];
  explanation: { label: string; text: string; matched: boolean }[];
};
export type ShareItem = {
  id: string; candidate: { id: string; code: string; name: string }; application_id: string; has_resume: boolean; link_expires_at: string | null;
  response: ShareResponse; response_label: string; feedback: string | null; responded_by: Person | null; responded_at: string | null;
  submission_code?: string; status?: SubmissionStatus; status_label?: string; status_changed_at?: string | null; rejection_reason?: string | null;
  rejection_reason_label?: string | null; next_action?: string | null; next_action_on?: string | null; acknowledged_at?: string | null;
  consent_reference?: string | null; match?: MatchBlock | null;
};
export type Share = {
  id: string; channel: ShareChannel; channel_label: string; requirement: { id: string; code: string; title: string }; company_id: string;
  contact: { id: string; name: string } | null; note: string | null; message: { id: string; delivery_status: string | null } | null;
  shared_by: Person; created_at: string; items: ShareItem[]; can_respond: boolean;
  recipient?: ShareRecipient; detail?: ShareDetail; detail_label?: string; consent_reference?: string | null; // pob-011 V10
  compensation_included?: boolean; follow_up?: { id: string; due_at: string; status: string } | null; // pob-021 B9, B10
};
export type SharePage = { items: Share[]; total: number; limit: number; offset: number };
export type Duplicate = { id: string; name: string; code: string };
export type SharedSummary = {
  code: string; name: string | null; qualification: string | null; college: string | null; passing_year: number | null; experience_months: number | null;
  current_company: string | null; location: string | null; preferred_locations: string[]; preferred_role: string | null; notice_days: number | null;
  skills: string[]; expected_salary?: string | null;
};
export type PortalItem = {
  id: string; shared_at: string; requirement: { code: string; title: string }; candidate: SharedSummary; has_resume: boolean;
  response: ShareResponse; response_label: string;
  submission_code?: string; match?: MatchBlock | null; status?: SubmissionStatus; status_label?: string; // pob-021
};
export type PortalPage = { items: PortalItem[]; total: number; limit: number; offset: number };

export const SHARE_LIMIT = 20;
export const NOTE_MAX = 500;
export const FEEDBACK_MAX = 1000;
export const PAGE_SIZE = 20;
export const CHANNELS: { key: ShareChannel; label: string; hint: string }[] = [
  { key: "email", label: "Email", hint: "One email to the contact, with a 7-day resume link per candidate." },
  { key: "whatsapp", label: "WhatsApp", hint: "Recorded now, then WhatsApp opens with the message ready to send." },
  { key: "portal", label: "Portal", hint: "Shown to the company's employer portal users under “Shared with you”." },
  { key: "other", label: "Other", hint: "Recorded only — for profiles shared another way." },
];
/** pob-011 V6/V7: what a vendor receives. */
export const VENDOR_DETAILS: { key: Exclude<ShareDetail, "named">; label: string; hint: string }[] = [
  { key: "anonymised", label: "Anonymised", hint: "Candidate code and profile only: no name, current company or resume." },
  { key: "full", label: "Full details", hint: "Name, email, mobile and resume. Needs the candidates' consent." },
];
export const CONSENT_MAX = 300;
/** pob-021 B8: what a client receives. */
export const CLIENT_DETAILS: { key: "named" | "anonymised"; label: string; hint: string }[] = [
  { key: "named", label: "Named", hint: "Name, profile summary and resume." },
  { key: "anonymised", label: "Anonymised", hint: "Candidate code and profile only: no name, current company or resume." },
];
export const STATUSES: { key: SubmissionStatus; label: string }[] = [
  { key: "submitted", label: "Submitted" }, { key: "client_reviewing", label: "Client reviewing" }, { key: "shortlisted", label: "Shortlisted" },
  { key: "interview", label: "Interview" }, { key: "on_hold", label: "On hold" }, { key: "rejected", label: "Rejected" },
  { key: "selected", label: "Selected" }, { key: "withdrawn", label: "Withdrawn" },
];
export const CLOSED_STATUSES: SubmissionStatus[] = ["rejected", "selected", "withdrawn"];
export const REJECTION_REASONS: { key: string; label: string }[] = [
  { key: "skills_mismatch", label: "Skills mismatch" }, { key: "experience_mismatch", label: "Experience mismatch" },
  { key: "compensation_mismatch", label: "Compensation mismatch" }, { key: "location_mismatch", label: "Location mismatch" },
  { key: "notice_period", label: "Notice period" }, { key: "duplicate_submission", label: "Duplicate submission" },
  { key: "position_filled", label: "Position filled" }, { key: "client_not_interested", label: "Client not interested" },
  { key: "candidate_withdrew", label: "Candidate withdrew" }, { key: "other", label: "Other" },
];
export const NEXT_ACTION_MAX = 300;

/** B14: "1 of 2 required · 0 of 1 preferred · gaps: Kafka" -- the API's wording in the email, without the score. */
export function matchSummary(match: MatchBlock | null | undefined): string | null {
  if (!match) return null;
  const required = match.required_matched.length + match.required_missing.length;
  const preferred = match.preferred_matched.length + match.preferred_missing.length;
  const parts = [];
  if (required) parts.push(`${match.required_matched.length} of ${required} required`);
  if (preferred) parts.push(`${match.preferred_matched.length} of ${preferred} preferred`);
  const gaps = [...match.required_missing, ...match.preferred_missing];
  if (gaps.length) parts.push(`gaps: ${gaps.join(", ")}`);
  return parts.length ? parts.join(" · ") : null;
}
export const RESPONSES: { key: ShareResponse; label: string }[] = [
  { key: "pending", label: "Pending" },
  { key: "interested", label: "Interested" },
  { key: "not_interested", label: "Not interested" },
  { key: "interview_requested", label: "Interview requested" },
];
/** S4: application statuses the API refuses to share, so their rows offer no "select to share" checkbox. */
export const UNSHAREABLE = ["rejected", "withdrawn", "joined"];
export const needsContact =(channel: ShareChannel) => channel === "email" || channel === "whatsapp";

export const SHARES_URL = "/api/v1/recruiter/shares";
export const EMPLOYER_SHARES_URL = "/api/v1/employer/shared-profiles";
const paged = (url: string, offset: number) => `${url}?limit=${PAGE_SIZE}&offset=${offset}`;
export const requirementSharesUrl = (id: string, offset = 0) => paged(`${REQUIREMENTS_URL}/${encodeURIComponent(id)}/shares`, offset);
export const companySharesUrl = (id: string, offset = 0) => paged(`/api/v1/recruiter/companies/${encodeURIComponent(id)}/shares`, offset);
export const shareItemUrl = (shareId: string, itemId: string) => `${SHARES_URL}/${encodeURIComponent(shareId)}/items/${encodeURIComponent(itemId)}`;
export const employerSharesUrl = (offset = 0) => paged(EMPLOYER_SHARES_URL, offset);
export const employerItemUrl = (itemId: string) => `${EMPLOYER_SHARES_URL}/${encodeURIComponent(itemId)}`;

export function isShareItem(data: unknown): data is ShareItem {
  const d = data as Partial<ShareItem> | null;
  return !!d && typeof d.id === "string" && !!d.candidate && typeof d.response === "string" && typeof d.has_resume === "boolean";
}

export function isShare(data: unknown): data is Share {
  const d = data as Partial<Share> | null;
  return !!d && typeof d.id === "string" && typeof d.channel === "string" && !!d.requirement && Array.isArray(d.items) && d.items.every(isShareItem)
    && typeof d.can_respond === "boolean";
}

export function isSharePage(data: unknown): data is SharePage {
  const d = data as Partial<SharePage> | null;
  return !!d && Array.isArray(d.items) && typeof d.total === "number" && d.items.every(isShare);
}

export function isShareBody(data: unknown): data is { share: Share; whatsapp_url: string | null } {
  const d = data as { share?: unknown; whatsapp_url?: unknown } | null;
  return !!d && isShare(d.share) && (d.whatsapp_url === null || typeof d.whatsapp_url === "string");
}

export function isPortalItem(data: unknown): data is PortalItem {
  const d = data as Partial<PortalItem> | null;
  return !!d && typeof d.id === "string" && !!d.candidate && Array.isArray(d.candidate.skills) && !!d.requirement && typeof d.response === "string";
}

export function isPortalPage(data: unknown): data is PortalPage {
  const d = data as Partial<PortalPage> | null;
  return !!d && Array.isArray(d.items) && typeof d.total === "number" && d.items.every(isPortalItem);
}

/** The repeat-share 409 (S5): `{message, duplicates}`; null for any other error detail. */
export function duplicatesOf(detail: unknown): { message: string; duplicates: Duplicate[] } | null {
  const d = detail as { message?: unknown; duplicates?: unknown } | null;
  return d && typeof d.message === "string" && Array.isArray(d.duplicates) ? { message: d.message, duplicates: d.duplicates as Duplicate[] } : null;
}

/** "2 yrs 2 mos" -- the API's wording in the email. */
export function experienceLabel(months: number | null): string | null {
  if (months === null) return null;
  const years = Math.floor(months / 12);
  const rest = months % 12;
  const parts = years ? [`${years} yr${years === 1 ? "" : "s"}`] : [];
  if (rest || !years) parts.push(`${rest} mo${rest === 1 ? "" : "s"}`);
  return parts.join(" ");
}
