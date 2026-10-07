import type { LeadMessage } from "@/lib/telecallerMessages";

// tel-013: one message as the API returns it, for the component tests.
export const message = (over: Partial<LeadMessage> = {}): LeadMessage => ({
  id: "M1", lead_id: "L1", channel: "whatsapp", template: { id: "T1", name: "Send Cyber Security Brochure" }, subject: null,
  body: "Hi Priya, here is the brochure", delivery_status: null, sent_at: "2026-09-13T05:05:00Z", sender: { id: "t1", full_name: "Tara Caller" },
  can_delete: true, ...over,
});

// tel-014: an email row (DEC-SCOPE-104 -- never deletable, with a delivery status).
export const emailMessage = (over: Partial<LeadMessage> = {}): LeadMessage =>
  message({ id: "E1", channel: "email", template: { id: "TE", name: "Course brochure" }, subject: "Your Python brochure", body: "Dear Priya",
    delivery_status: "sent", can_delete: false, ...over });
