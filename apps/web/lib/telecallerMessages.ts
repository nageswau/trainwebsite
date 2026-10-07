// tel-013 (DEC-SCOPE-099): messages to a lead -- types, the endpoints, wa.me links and the "WhatsApp sent" line. The API decides scope, every
// rule and `can_delete` (the sender, on the send's IST day, lead not handed over); the UI only offers what it allows.
import { SCHOOL_TIME_ZONE } from "@/lib/formatDate";
import { CATALOGUE_PAGE_SIZE, getPage } from "@/lib/telecallerCatalogue";
import { TEMPLATES_URL, type Template } from "@/lib/telecallerContent";
import { leadUrl, type PersonRef } from "@/lib/telecallerLeads";

export type LeadMessage = {
  id: string; lead_id: string; channel: "whatsapp" | "email"; template: { id: string; name: string } | null; subject: string | null; body: string;
  sent_at: string; sender: PersonRef; can_delete: boolean;
};
export type RenderedTemplate = {
  template: { id: string; name: string; channel: string; kind: string }; subject: string | null; body: string;
  brochure_link: { url: string; expires_at: string } | null; product_mismatch: boolean;
};

export const BODY_MAX = 1000; // tel-012's WhatsApp limit
export const LIST_LIMIT = 50;
export const leadMessagesUrl = (leadId: string) => leadUrl(leadId, `/messages?limit=${LIST_LIMIT}`);
export const createMessageUrl = (leadId: string) => leadUrl(leadId, "/messages");
export const messageUrl = (id: string) => `/api/v1/telecaller/messages/${encodeURIComponent(id)}`;
export const renderUrl = (leadId: string, templateId: string) => leadUrl(leadId, `/render?template_id=${encodeURIComponent(templateId)}`);

/** D1: `to` is the API's `whatsapp_to` (E.164 digits); the text is the composer's, URL-encoded (tel-012 renders plain text). */
export const waHref = (to: string, text: string) => `https://wa.me/${to}${text ? `?text=${encodeURIComponent(text)}` : ""}`;

/** AC2 / EVID-019 L452: "WhatsApp sent – 13 Sept 2026 – 10:35 AM", in India time. */
export function sentLabel(sentAt: string): string {
  const at = new Date(sentAt);
  const day = at.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: SCHOOL_TIME_ZONE });
  const time = at.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true, timeZone: SCHOOL_TIME_ZONE });
  return `WhatsApp sent – ${day} – ${time}`;
}

export function isLeadMessage(data: unknown): data is LeadMessage {
  const d = data as Partial<LeadMessage> | null;
  return !!d && typeof d.id === "string" && typeof d.sent_at === "string" && typeof d.body === "string" && typeof d.can_delete === "boolean";
}

export function isRenderedTemplate(data: unknown): data is RenderedTemplate {
  const d = data as Partial<RenderedTemplate> | null;
  return !!d && typeof d.body === "string" && typeof d.product_mismatch === "boolean";
}

/** The composer's picker: every active WhatsApp template, page after page (tel-002 QA-01). */
export async function activeWhatsAppTemplates(signal?: AbortSignal): Promise<Template[]> {
  const items: Template[] = [];
  for (;;) {
    const page = await getPage<Template>(`${TEMPLATES_URL}?channel=whatsapp&active=true&limit=${CATALOGUE_PAGE_SIZE}&offset=${items.length}`, signal);
    items.push(...page.items);
    if (page.items.length === 0 || items.length >= page.total) return items;
  }
}
