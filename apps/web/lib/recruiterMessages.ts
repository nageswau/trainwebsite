// rec-026 (DEC-SCOPE-135): recruiter messages -- the template library's types and EVID-018 §19 kind labels, the endpoints, the composer
// targets for a company contact or a candidate, and the message line. The API decides scope and every rule (MS4-MS9); the UI only offers
// what it allows. A message is permanent (MS9): there is no edit or delete.
import { CATALOGUE_PAGE_SIZE, getPage } from "@/lib/telecallerCatalogue";
import { sentLabel, type ComposerTarget, type DeliveryStatus } from "@/lib/telecallerMessages";

export type Channel = "whatsapp" | "email";
export type RecTemplate = { id: string; channel: Channel; kind: string; name: string; subject: string | null; body: string; active: boolean };
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

/** The placeholders the API would refuse (MS2): any `{...}` that is not one of the three, spelled exactly. */
export const unknownPlaceholders = (text: string) => [...new Set([...text.matchAll(/\{([^{}\n]*)\}/g)].map((m) => m[1]).filter((t) => !PLACEHOLDERS.includes(t)))].map((t) => `{${t}}`);

export const TEMPLATES_URL = "/api/v1/recruiter/templates";
export const MESSAGES_URL = "/api/v1/recruiter/messages";
export const LIST_LIMIT = 50;
export const companyMessagesUrl = (companyId: string) => `/api/v1/recruiter/companies/${encodeURIComponent(companyId)}/messages?limit=${LIST_LIMIT}`;
export const candidateMessagesUrl = (candidateId: string) => `/api/v1/recruiter/candidates/${encodeURIComponent(candidateId)}/messages?limit=${LIST_LIMIT}`;

/** A composer's picker: every active template of the channel, page after page. */
export async function activeTemplates(channel: Channel, signal?: AbortSignal): Promise<RecTemplate[]> {
  const items: RecTemplate[] = [];
  for (;;) {
    const page = await getPage<RecTemplate>(`${TEMPLATES_URL}?channel=${channel}&active=true&limit=${CATALOGUE_PAGE_SIZE}&offset=${items.length}`, signal);
    items.push(...page.items);
    if (page.items.length === 0 || items.length >= page.total) return items;
  }
}

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

const EMAIL_STATUS: Record<DeliveryStatus, string> = {
  queued: "Email sending", sending: "Email sending", retrying: "Email delayed", sent: "Email sent", failed: "Email failed",
};
/** "Email sent – 8 Oct 2026 – 10:35 AM" / "WhatsApp sent – …", in India time (tel-013's line). */
export const messageTitle = (m: RecMessage) => sentLabel(m.sent_at, m.channel === "email" ? EMAIL_STATUS[m.delivery_status ?? "queued"] : "WhatsApp sent");
/** The worker picks these up within seconds, so the list refreshes; a `retrying` email waits minutes and doesn't. */
export const isPending = (m: RecMessage) => m.delivery_status === "queued" || m.delivery_status === "sending";
