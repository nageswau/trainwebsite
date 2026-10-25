// ccrm-037 (DEC-SCOPE-273): the counselor's messages to a student -- the Overseas Admin's template library (MT1/MT2), the endpoints and the
// composer target, whose application id rides on the render query and the send body (MT4). The API decides scope and every rule; the UI
// only offers what it allows. Messages and replies are permanent (MT8): there is no edit or delete.
import type { Page } from "@/lib/apiErrors";
import { templatesFrom, type Channel, type TemplateLibrary } from "@/lib/recruiterMessages";
import type { ComposerTarget, DeliveryStatus } from "@/lib/telecallerMessages";

export const TEMPLATES_URL = "/api/v1/counselor/templates";
export const TEMPLATES_PATH = "/overseas/admin/message-templates";
export const LIST_LIMIT = 50;
const studentUrl = (studentId: string, tail: string) => `/api/v1/counselor/students/${encodeURIComponent(studentId)}/${tail}`;
/** The 360 page reads one row for the recipient and the applications; the section reads the list. */
export const studentMessagesUrl = (studentId: string, limit = LIST_LIMIT) => studentUrl(studentId, `messages?limit=${limit}`);
export const replyUrl = (studentId: string) => studentUrl(studentId, "replies");

type Ref = { id: string; name: string };
export type StudentApplicationRef = { id: string; label: string };
export type StudentMessage = {
  id: string; student_id: string; application: StudentApplicationRef | null; direction: "outbound" | "inbound"; channel: Channel;
  template: Ref | null; subject: string | null; body: string; delivery_status: DeliveryStatus | null; sent_at: string;
  sender: { id: string; full_name: string };
};
export type StudentRecipient = { name: string; email: string; whatsapp_to: string | null; whatsapp_opt_in: boolean }; // ccrm-040 CN7
/** The list also says who the student is (their wa.me number, MT3) and which applications a message may be about (MT4). */
export type StudentMessagesPage = Page<StudentMessage> & { recipient: StudentRecipient; applications: StudentApplicationRef[] };

export const COUNSELOR_LIBRARY: TemplateLibrary = {
  url: TEMPLATES_URL, kinds: null,
  placeholders: ["name", "university", "course", "intake", "application_deadline", "offer_deadline", "counselor"],
  placeholderHint:
    "Placeholders: {name} (the student), {university}, {course}, {intake}, {application_deadline}, {offer_deadline} (from the application the message is about), {counselor} (the sender).",
  sampleNote: "Sample values: Priya Sharma, MSc Computer Science at University of Example (Sep 2027), and your name as the counselor.",
  deactivateHint: "It disappears from the counselors' pickers; messages already sent keep its name.",
};

const loadTemplates = templatesFrom(TEMPLATES_URL); // one function, so a composer's picker loads once

/** The composers' endpoints for one student; `applicationId` is "" for a general message. */
export function studentTarget(studentId: string, applicationId: string): ComposerTarget {
  const about = applicationId ? `&application_id=${encodeURIComponent(applicationId)}` : "";
  return {
    loadTemplates,
    renderUrl: (templateId) => `${studentUrl(studentId, "messages/render")}?template_id=${encodeURIComponent(templateId)}${about}`,
    createUrl: studentUrl(studentId, "messages"),
    payload: applicationId ? { application_id: applicationId } : {},
  };
}
