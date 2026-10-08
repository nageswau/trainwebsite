import { describe, expect, it } from "vitest";

import { KINDS, candidateMessagesUrl, isPending, kindLabel, messageTitle, recruiterTarget, unknownPlaceholders, type RecMessage } from "@/lib/recruiterMessages";
import { leadTarget } from "@/lib/telecallerMessages";

const message = (over: Partial<RecMessage>): RecMessage => ({
  id: "m1", kind: "candidate", company_id: null, contact: null, candidate: { id: "c1", name: "Rahul", code: "CAN-000001" }, channel: "email",
  template: null, subject: "S", body: "B", delivery_status: "queued", sent_at: "2026-10-08T05:05:00Z", sender: { id: "u1", full_name: "Asha" }, ...over,
});

describe("rec-026 recruiterMessages", () => {
  it("lists the 12 source kinds in source order (AC1)", () => {
    expect(KINDS.whatsapp.map((k) => k.label)).toEqual(["Candidate profiles", "JD confirmation", "Interview reminders", "Follow-up", "Requirement updates"]);
    expect(KINDS.email.map((k) => k.label)).toEqual([
      "Company introduction", "Recruitment proposal", "Candidate profiles", "JD acknowledgement", "Interview confirmation", "Offer follow-up", "Joining confirmation",
    ]);
    expect(kindLabel("email", "offer_follow_up")).toBe("Offer follow-up");
    expect(kindLabel("email", "unknown")).toBe("unknown");
  });

  it("flags only the placeholders the API would refuse", () => {
    expect(unknownPlaceholders("Hi {name} at {company} – {recruiter}")).toEqual([]);
    expect(unknownPlaceholders("Hi {Name} {student} {student} { lone")).toEqual(["{Name}", "{student}"]);
  });

  it("puts the party on the render query and the send body", () => {
    const contact = recruiterTarget({ kind: "contact", id: "k 1", name: "Priya", whatsappTo: "919876543210", email: null });
    expect(contact.renderUrl("t1")).toBe("/api/v1/recruiter/messages/render?template_id=t1&contact_id=k%201");
    expect(contact.createUrl).toBe("/api/v1/recruiter/messages");
    expect(contact.payload).toEqual({ contact_id: "k 1" });
    expect(recruiterTarget({ kind: "candidate", id: "c1", name: "R", whatsappTo: null, email: "r@x.test" }).payload).toEqual({ candidate_id: "c1" });
    expect(candidateMessagesUrl("c1")).toBe("/api/v1/recruiter/candidates/c1/messages?limit=50");
  });

  it("keeps the lead target on the tel-013 endpoints", () => {
    const target = leadTarget("L1");
    expect(target.createUrl).toContain("/L1/messages");
    expect(target.renderUrl("t1")).toContain("/L1/render?template_id=t1");
    expect(target.payload).toBeUndefined();
  });

  it("names where an email stands and polls only while it is queued or sending (AC2)", () => {
    expect(messageTitle(message({}))).toBe("Email sending – 8 Oct 2026 – 10:35 AM");
    expect(messageTitle(message({ delivery_status: "sent" }))).toMatch(/^Email sent – /);
    expect(messageTitle(message({ channel: "whatsapp", delivery_status: null, subject: null }))).toMatch(/^WhatsApp sent – /);
    expect(isPending(message({}))).toBe(true);
    expect(isPending(message({ delivery_status: "retrying" }))).toBe(false);
  });
});
