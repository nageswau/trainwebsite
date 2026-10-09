// upc-012 (DEC-SCOPE-138): calls, WhatsApp and email kept on a university -- types, endpoints, the partnership template library (UC4/UC5)
// and the composer target for one contact. The API decides scope and every rule (UC1-UC9); the UI only offers what it allows. Calls and
// messages are permanent: there is no edit or delete.
import type { DeliveryStatus } from "@/lib/telecallerMessages";
import { templatesFrom, type Channel, type TemplateLibrary } from "@/lib/recruiterMessages";
import type { ComposerTarget } from "@/lib/telecallerMessages";

/** UC3: who reads a university's calls and messages (overseas_admin reads the master only). */
export const COMMS_READERS = new Set(["partnership_manager", "partnership_head", "super_admin"]);
export const LIST_LIMIT = 50;
export const TEMPLATES_URL = "/api/v1/partnership/templates";
export const MESSAGES_URL = "/api/v1/partnership/messages";
export const CALLS_URL = "/api/v1/partnership/calls";
export const TEMPLATES_PATH = "/partnership/head/templates";
const historyUrl = (universityId: string, kind: "calls" | "messages") =>
  `/api/v1/partnership/universities/${encodeURIComponent(universityId)}/${kind}?limit=${LIST_LIMIT}`;
export const universityCallsUrl = (universityId: string) => historyUrl(universityId, "calls");
export const universityMessagesUrl = (universityId: string) => historyUrl(universityId, "messages");

type Ref = { id: string; name: string };
type Person = { id: string; full_name: string };
export type UniversityCall = {
  id: string; university_id: string; contact: Ref | null; occurred_at: string; duration_seconds: number | null; direction: "outgoing" | "incoming";
  outcome: string; outcome_label: string; connected: boolean; notes: string | null; next_follow_up_on: string | null; caller: Person; created_at: string;
};
export type UniversityMessage = {
  id: string; university_id: string; contact: Ref | null; channel: Channel; template: Ref | null; subject: string | null; body: string;
  delivery_status: DeliveryStatus | null; sent_at: string; sender: Person;
};

export const PARTNERSHIP_LIBRARY: TemplateLibrary = {
  url: TEMPLATES_URL, kinds: null, placeholders: ["name", "university", "manager"],
  placeholderHint: "Placeholders: {name} (the contact), {university} (the university's name), {manager} (the sender).",
  sampleNote: "Sample values: Priya Sharma at University of Example, and your name as the manager.",
  deactivateHint: "It disappears from the managers' pickers; messages already sent keep its name.",
};

const loadTemplates = templatesFrom(TEMPLATES_URL); // one function, so a composer's picker loads once

/** The composers' endpoints for one contact: its id rides on the render query and the send body. */
export function contactTarget(contactId: string): ComposerTarget {
  return {
    loadTemplates,
    renderUrl: (templateId) => `${MESSAGES_URL}/render?template_id=${encodeURIComponent(templateId)}&contact_id=${encodeURIComponent(contactId)}`,
    createUrl: MESSAGES_URL,
    payload: { contact_id: contactId },
  };
}
