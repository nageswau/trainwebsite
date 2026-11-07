// rec-026 (DEC-SCOPE-135): recruiter messages -- the template library's types and EVID-018 §19 kind labels, the endpoints, the composer
// targets for a company contact or a candidate, and the message line. The API decides scope and every rule (MS4-MS9); the UI only offers
// what it allows. A message is permanent (MS9): there is no edit or delete.
import { CATALOGUE_PAGE_SIZE, getPage } from "@/lib/telecallerCatalogue";
import type { ComposerTarget, DeliveryStatus } from "@/lib/telecallerMessages";

export type Channel = "whatsapp" | "email";
export type RecTemplate = { id: string; channel: Channel; kind: string; name: string; subject: string | null; body: string; active: boolean };
/** A template of either library; upc-012's have no kind. */
export type MessageTemplate = Omit<RecTemplate, "kind"> & { kind?: string };
export type RecMessage = {
  id: string; kind: "contact" | "candidate"; company_id: string | null; contact: { id: string; name: string } | null;
  candidate: { id: string; name: string; code: string } | null; channel: Channel; template: { id: string; name: string } | null;
  subject: string | null; body: string; delivery_status: DeliveryStatus | null; sent_at: string; sender: { id: string; full_name: string };
};
/** The recipient a composer writes to: a company contact or a candidate (ccrm-037: or an overseas student). */
// ccrm-040 (DEC-SCOPE-276 CN7): `whatsappOff` says why WhatsApp is unavailable when it is not a missing number (a student who has not opted in).
export type Party = { kind: "contact" | "candidate" | "student"; id: string; name: string; whatsappTo: string | null; email: string | null; whatsappOff?: string };

/** EVID-018 §19 in source order and wording (WhatsApp L766-L776, email L778-L792). */
export const KINDS: Record<Channel, { key: string; label: string }[]> = {
  whatsapp: [
    { key: "candidate_profiles", label: "Candidate profiles" }, { key: "jd_confirmation", label: "JD confirmation" },
    { key: "interview_reminder", label: "Interview reminders" }, { key: "follow_up", label: "Follow-up" },
    { key: "requirement_update", label: "Requirement updates" },
  ],
  email: [
    { key: "company_introduction", label: "Company introduction" }, { key: "recruitment_proposal", label: "Recruitment proposal" },
    { key: "candidate_profiles", label: "Candidate profiles" }, { key: "jd_acknowledgement", label: "JD acknowledgement" },
    { key: "interview_confirmation", label: "Interview confirmation" }, { key: "offer_follow_up", label: "Offer follow-up" },
    { key: "joining_confirmation", label: "Joining confirmation" },
  ],
};
export const kindLabel = (channel: Channel, key: string) => KINDS[channel].find((k) => k.key === key)?.label ?? key;
export const CHANNEL_LABEL: Record<Channel, string> = { whatsapp: "WhatsApp", email: "Email" };
export const BODY_LIMIT: Record<Channel, number> = { whatsapp: 1000, email: 5000 };
export const PLACEHOLDERS = ["name", "company", "recruiter"];
export const PLACEHOLDER_HINT = "Placeholders: {name} (the recipient), {company} (the contact's company; empty for a candidate), {recruiter} (you).";

/** The placeholders the API would refuse (MS2): any `{...}` that is not one of the library's, spelled exactly. */
export const unknownPlaceholders = (text: string, allowed: readonly string[] = PLACEHOLDERS) =>
  [...new Set([...text.matchAll(/\{([^{}\n]*)\}/g)].map((m) => m[1]).filter((t) => !allowed.includes(t)))].map((t) => `{${t}}`);

export const TEMPLATES_URL = "/api/v1/recruiter/templates";
export const MESSAGES_URL = "/api/v1/recruiter/messages";
export const LIST_LIMIT = 50;
export const companyMessagesUrl = (companyId: string) => `/api/v1/recruiter/companies/${encodeURIComponent(companyId)}/messages?limit=${LIST_LIMIT}`;
export const candidateMessagesUrl = (candidateId: string) => `/api/v1/recruiter/candidates/${encodeURIComponent(candidateId)}/messages?limit=${LIST_LIMIT}`;

/** A composer's picker: every active template of the channel at `url`, page after page (upc-012 reuses it for its own library). */
export const templatesFrom = (url: string) => async (channel: Channel, signal?: AbortSignal): Promise<MessageTemplate[]> => {
  const items: MessageTemplate[] = [];
  for (;;) {
    const page = await getPage<MessageTemplate>(`${url}?channel=${channel}&active=true&limit=${CATALOGUE_PAGE_SIZE}&offset=${items.length}`, signal);
    items.push(...page.items);
    if (page.items.length === 0 || items.length >= page.total) return items;
  }
};
export const activeTemplates = templatesFrom(TEMPLATES_URL);

/** upc-012: what the templates panel needs to know about a library -- the recruiter's (rec-026) or the partnership head's. `kinds` is null
 *  when the library has none. */
export type TemplateLibrary = {
  url: string; kinds: Record<Channel, { key: string; label: string }[]> | null; placeholders: readonly string[]; placeholderHint: string;
  sampleNote: string; deactivateHint: string;
};
export const RECRUITER_LIBRARY: TemplateLibrary = {
  url: TEMPLATES_URL, kinds: KINDS, placeholders: PLACEHOLDERS, placeholderHint: PLACEHOLDER_HINT,
  sampleNote: "Sample values: Priya Sharma at Acme Technologies, and your name as the recruiter.",
  deactivateHint: "It disappears from the recruiters' pickers; messages already sent keep its name.",
};

// --- pob-023 (DEC-SCOPE-408): the governed library -----------------------------------------------------------------------------------
export type TemplateChannel = Channel | "linkedin" | "call";
export type CopyChannel = "linkedin" | "call";
export type TemplateStatus = "draft" | "approved" | "archived";
export const TEMPLATE_CHANNELS: { key: TemplateChannel; label: string }[] = [
  { key: "whatsapp", label: "WhatsApp" }, { key: "email", label: "Email" }, { key: "linkedin", label: "LinkedIn" }, { key: "call", label: "Calling script" },
];
export const templateChannelLabel = (channel: TemplateChannel) => TEMPLATE_CHANNELS.find((c) => c.key === channel)?.label ?? channel;
/** §14's six categories, in source order. */
export const TEMPLATE_CATEGORIES: { key: string; label: string }[] = [
  { key: "company", label: "Company" }, { key: "linkedin", label: "LinkedIn" }, { key: "whatsapp", label: "WhatsApp" },
  { key: "calling", label: "Calling" }, { key: "college_tpo", label: "College/TPO" }, { key: "candidate", label: "Candidate" },
];
export const categoryLabel = (key: string) => TEMPLATE_CATEGORIES.find((c) => c.key === key)?.label ?? key;
/** The category a new template starts with (the API's G2 default, so the form agrees with it). */
export const DEFAULT_CATEGORY: Record<TemplateChannel, string> = { whatsapp: "whatsapp", email: "company", linkedin: "linkedin", call: "calling" };
export const STATUS_LABEL: Record<TemplateStatus, string> = { draft: "Draft", approved: "Approved", archived: "Archived" };
export const GOVERNED_BODY_LIMIT: Record<TemplateChannel, number> = { whatsapp: 1000, email: 5000, linkedin: 2000, call: 5000 };
export const STEPS_MAX = 20;
/** G8: the API's allow-list, with what each fills in. */
export const GOVERNED_PLACEHOLDERS: { key: string; label: string }[] = [
  { key: "name", label: "the recipient" }, { key: "company", label: "the contact's company" }, { key: "recruiter", label: "you" },
  { key: "designation", label: "the contact's designation" }, { key: "job_title", label: "the requirement's title" },
  { key: "job_location", label: "the requirement's location" }, { key: "package_range", label: "the salary range (needs the client commercials permission)" },
  { key: "candidate", label: "the candidate" }, { key: "interview_date", label: "the interview date" }, { key: "interview_time", label: "the interview time" },
  { key: "interview_mode", label: "the interview mode" }, { key: "interview_link", label: "the meeting link or location" },
];
export const GOVERNED_PLACEHOLDER_KEYS = GOVERNED_PLACEHOLDERS.map((p) => p.key);
type Person = { id: string; full_name: string } | null;
export type GovernedTemplate = {
  id: string; channel: TemplateChannel; kind: string | null; name: string; subject: string | null; body: string; active: boolean;
  category: string; purpose: string | null; language: string; department: string | null; industry: string | null; role_type: string | null;
  status: TemplateStatus; visibility: "shared" | "personal"; steps: string[] | null; version: number; created_by: Person; updated_by: Person;
  created_at: string; updated_at: string; last_used_at: string | null; can_edit: boolean; can_approve: boolean; can_archive: boolean; can_restore: boolean;
};
export type TemplateVersion = Omit<GovernedTemplate, "id" | "channel" | "active" | "status" | "visibility" | "version" | "created_by" | "updated_by" | "updated_at" | "last_used_at" | "can_edit" | "can_approve" | "can_archive" | "can_restore"> & {
  version: number; edited_by: Person;
};
export const templateUrl = (id: string, action = "") => `${TEMPLATES_URL}/${encodeURIComponent(id)}${action ? `/${action}` : ""}`;
export const COPIES_URL = `${MESSAGES_URL}/copies`;

// --- pob-007 (DEC-SCOPE-421 A1/A3): LinkedIn outreach logged by hand, and a message's outcome ------------------------------------------
export const LINKEDIN_URL = `${MESSAGES_URL}/linkedin`;
export const messageOutcomeUrl = (id: string) => `${MESSAGES_URL}/${encodeURIComponent(id)}/outcome`;
export const LINKEDIN_ACTIONS = [{ key: "connection_request", label: "Connection request" }, { key: "message", label: "Message" }] as const;
export type LinkedInAction = (typeof LINKEDIN_ACTIONS)[number]["key"];
/** "LinkedIn connection request sent" / "LinkedIn message sent". */
export const linkedinTitle = (action: string | null | undefined) =>
  action === "connection_request" ? "LinkedIn connection request sent" : "LinkedIn message sent";
export const MESSAGE_OUTCOME_MAX = 500;

/** What a composer may use (G5): approved shared templates and the caller's own personal ones, page after page. */
export const usableTemplates = async (channel: TemplateChannel, signal?: AbortSignal): Promise<GovernedTemplate[]> => {
  const items: GovernedTemplate[] = [];
  for (;;) {
    const page = await getPage<GovernedTemplate>(`${TEMPLATES_URL}?channel=${channel}&usable=true&limit=${CATALOGUE_PAGE_SIZE}&offset=${items.length}`, signal);
    items.push(...page.items);
    if (page.items.length === 0 || items.length >= page.total) return items;
  }
};

/** G8/G12: the record a message is about -- its values fill the requirement or interview placeholders. */
export type MessageContext = { jobId?: string; interviewId?: string };
const contextQuery = (context?: MessageContext) =>
  (context?.jobId ? `&job_id=${encodeURIComponent(context.jobId)}` : "") + (context?.interviewId ? `&interview_id=${encodeURIComponent(context.interviewId)}` : "");

/** The composers' endpoints for one party: the party id rides on the render query and the send body. pob-023: the picker offers what
 *  the caller may use (their personal templates too), and an optional context fills the requirement/interview placeholders. */
export function recruiterTarget(party: Party, context?: MessageContext): ComposerTarget {
  const key = party.kind === "contact" ? "contact_id" : "candidate_id";
  return {
    loadTemplates: usableTemplates,
    renderUrl: (templateId) => `${MESSAGES_URL}/render?template_id=${encodeURIComponent(templateId)}&${key}=${encodeURIComponent(party.id)}${contextQuery(context)}`,
    createUrl: MESSAGES_URL,
    payload: { [key]: party.id },
  };
}

/** tel-013/014's message line ("Email sent – 8 Oct 2026 – 10:35 AM", in India time) and its "still being delivered" test, shared. */
export { isPending, messageTitle } from "@/lib/telecallerMessages";
