import type { LeadMessage } from "@/lib/telecallerMessages";

// tel-013: one message as the API returns it, for the component tests.
export const message = (over: Partial<LeadMessage> = {}): LeadMessage => ({
  id: "M1", lead_id: "L1", channel: "whatsapp", template: { id: "T1", name: "Send Cyber Security Brochure" }, subject: null,
  body: "Hi Priya, here is the brochure", sent_at: "2026-09-13T05:05:00Z", sender: { id: "t1", full_name: "Tara Caller" }, can_delete: true, ...over,
});
