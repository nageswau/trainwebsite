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
/** The recipient a composer writes to: a company contact or a candidate. */
export type Party = { kind: "contact" | "candidate"; id: string; name: string; whatsappTo: string | null; email: string | null };

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

/** The composers' endpoints for one party: the party id rides on the render query and the send body. */
export function recruiterTarget(party: Party): ComposerTarget {
  const key = party.kind === "contact" ? "contact_id" : "candidate_id";
  return {
    loadTemplates: activeTemplates,
    renderUrl: (templateId) => `${MESSAGES_URL}/render?template_id=${encodeURIComponent(templateId)}&${key}=${encodeURIComponent(party.id)}`,
    createUrl: MESSAGES_URL,
    payload: { [key]: party.id },
  };
}

/** tel-013/014's message line ("Email sent – 8 Oct 2026 – 10:35 AM", in India time) and its "still being delivered" test, shared. */
export { isPending, messageTitle } from "@/lib/telecallerMessages";
