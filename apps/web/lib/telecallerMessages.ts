// tel-013 (DEC-SCOPE-100): messages to a lead -- types, the endpoints, wa.me links and the "WhatsApp sent" line. The API decides scope, every
// rule and `can_delete` (the sender, on the send's IST day, lead not handed over); the UI only offers what it allows. tel-014 (DEC-SCOPE-106)
// adds email: a subject and a delivery status the worker moves on (queued -> sending -> sent | retrying | failed); never deletable.
import { SCHOOL_TIME_ZONE } from "@/lib/formatDate";
import { CATALOGUE_PAGE_SIZE, getPage } from "@/lib/telecallerCatalogue";
import { TEMPLATES_URL, type Template } from "@/lib/telecallerContent";
import { leadUrl, type PersonRef } from "@/lib/telecallerLeads";

export type DeliveryStatus = "queued" | "sending" | "retrying" | "sent" | "failed";
export type LeadMessage = {
  id: string; lead_id: string; channel: "whatsapp" | "email"; template: { id: string; name: string } | null; subject: string | null; body: string;
  delivery_status: DeliveryStatus | null; sent_at: string; sender: PersonRef; can_delete: boolean;
};
export type RenderedTemplate = {
  template: { id: string; name: string; channel: string; kind: string }; subject: string | null; body: string;
  brochure_link?: { url: string; expires_at: string } | null; product_mismatch?: boolean; // tel-013 only; rec-026's render has neither
};

export const BODY_MAX = 1000; // tel-012's WhatsApp limit
export const EMAIL_BODY_MAX = 5000; // tel-012's email limits
export const SUBJECT_MAX = 200;
export const LIST_LIMIT = 50;
export const leadMessagesUrl = (leadId: string) => leadUrl(leadId, `/messages?limit=${LIST_LIMIT}`);
export const createMessageUrl = (leadId: string) => leadUrl(leadId, "/messages");
export const messageUrl = (id: string) => `/api/v1/telecaller/messages/${encodeURIComponent(id)}`;
export const renderUrl = (leadId: string, templateId: string) => leadUrl(leadId, `/render?template_id=${encodeURIComponent(templateId)}`);

/** D1: `to` is the API's `whatsapp_to` (E.164 digits); the text is the composer's, URL-encoded (tel-012 renders plain text). */
export const waHref = (to: string, text: string) => `https://wa.me/${to}${text ? `?text=${encodeURIComponent(text)}` : ""}`;

/** AC2 / EVID-019 L452: "WhatsApp sent – 13 Sept 2026 – 10:35 AM", in India time. */
export function sentLabel(sentAt: string, what = "WhatsApp sent"): string {
  const at = new Date(sentAt);
  const day = at.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: SCHOOL_TIME_ZONE });
  const time = at.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true, timeZone: SCHOOL_TIME_ZONE });
  return `${what} – ${day} – ${time}`;
}

const EMAIL_STATUS: Record<DeliveryStatus, string> = {
  queued: "Email sending", sending: "Email sending", retrying: "Email delayed", sent: "Email sent", failed: "Email failed",
};

/** tel-014 E5: an email's line names where its delivery stands; the time is when it was sent from the CRM. */
export const messageTitle = (m: LeadMessage) =>
  sentLabel(m.sent_at, m.channel === "email" ? EMAIL_STATUS[m.delivery_status ?? "queued"] : "WhatsApp sent");

/** The worker picks these up within seconds, so the list refreshes; a `retrying` email waits minutes and doesn't. */
export const isPending = (m: LeadMessage) => m.delivery_status === "queued" || m.delivery_status === "sending";

export function isRenderedTemplate(data: unknown): data is RenderedTemplate {
  const d = data as Partial<RenderedTemplate> | null;
  return !!d && typeof d.body === "string";
}

/** A composer's picker: every active template of the channel, page after page (tel-002 QA-01). */
export async function activeTemplates(channel: "whatsapp" | "email", signal?: AbortSignal): Promise<Template[]> {
  const items: Template[] = [];
  for (;;) {
    const page = await getPage<Template>(`${TEMPLATES_URL}?channel=${channel}&active=true&limit=${CATALOGUE_PAGE_SIZE}&offset=${items.length}`, signal);
    items.push(...page.items);
    if (page.items.length === 0 || items.length >= page.total) return items;
  }
}

/** rec-026: where a composer reads its templates and render, and posts the send -- a lead's here, a recruiter party's in recruiterMessages.
 *  `payload` is merged into the send body (e.g. the party id). */
export type ComposerTarget = {
  loadTemplates: (channel: "whatsapp" | "email", signal?: AbortSignal) => Promise<{ id: string; name: string }[]>;
  renderUrl: (templateId: string) => string;
  createUrl: string;
  payload?: Record<string, unknown>;
};
export const leadTarget = (leadId: string): ComposerTarget => ({
  loadTemplates: activeTemplates, renderUrl: (templateId) => renderUrl(leadId, templateId), createUrl: createMessageUrl(leadId),
});
