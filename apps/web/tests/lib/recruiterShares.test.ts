import { describe, expect, it } from "vitest";

import {
  CHANNELS,
  companySharesUrl,
  duplicatesOf,
  employerItemUrl,
  experienceLabel,
  isPortalPage,
  isShareBody,
  isSharePage,
  needsContact,
  requirementSharesUrl,
  RESPONSES,
  shareItemUrl,
  type Share,
} from "@/lib/recruiterShares";

const share = (over: Partial<Share> = {}): Share => ({
  id: "S1", channel: "email", channel_label: "Email", requirement: { id: "J1", code: "REQ-000001", title: "Java Dev" }, company_id: "CO1",
  contact: { id: "K1", name: "Priya" }, note: null, message: { id: "M1", delivery_status: "queued" }, shared_by: { id: "U1", full_name: "Asha" },
  created_at: "2026-10-09T05:00:00Z", can_respond: true,
  items: [{ id: "I1", candidate: { id: "C1", code: "CAN-000001", name: "Rahul" }, application_id: "A1", has_resume: true, link_expires_at: null,
    response: "pending", response_label: "Pending", feedback: null, responded_by: null, responded_at: null }],
  ...over,
});

describe("rec-019 recruiterShares", () => {
  it("offers the four §11 channels and the four responses; only email and WhatsApp need a contact", () => {
    expect(CHANNELS.map((c) => c.label)).toEqual(["Email", "WhatsApp", "Portal", "Other"]);
    expect(RESPONSES.map((r) => r.key)).toEqual(["pending", "interested", "not_interested", "interview_requested"]);
    expect(CHANNELS.filter((c) => needsContact(c.key)).map((c) => c.key)).toEqual(["email", "whatsapp"]);
  });

  it("builds the URLs", () => {
    expect(requirementSharesUrl("J 1", 20)).toBe("/api/v1/recruiter/requirements/J%201/shares?limit=20&offset=20");
    expect(companySharesUrl("CO1")).toBe("/api/v1/recruiter/companies/CO1/shares?limit=20&offset=0");
    expect(shareItemUrl("S1", "I1")).toBe("/api/v1/recruiter/shares/S1/items/I1");
    expect(employerItemUrl("I1")).toBe("/api/v1/employer/shared-profiles/I1");
  });

  it("guards the bodies", () => {
    expect(isSharePage({ items: [share()], total: 1, limit: 20, offset: 0 })).toBe(true);
    expect(isSharePage({ items: [{ id: "x" }], total: 1 })).toBe(false);
    expect(isShareBody({ share: share(), whatsapp_url: null })).toBe(true);
    expect(isShareBody({ share: share() })).toBe(false);
    expect(isPortalPage({ items: [], total: 0 })).toBe(true);
    expect(isPortalPage({ items: [{ id: "I1", candidate: { skills: "x" }, requirement: {}, response: "pending" }], total: 1 })).toBe(false);
  });

  it("reads the repeat-share 409 only", () => {
    const detail = { message: "1 of these candidates were already shared", duplicates: [{ id: "C1", name: "Rahul", code: "CAN-000001" }] };
    expect(duplicatesOf(detail)).toEqual(detail);
    expect(duplicatesOf("Choose active candidates from the pool")).toBeNull();
  });

  it("words experience like the email", () => {
    expect(experienceLabel(26)).toBe("2 yrs 2 mos");
    expect(experienceLabel(12)).toBe("1 yr");
    expect(experienceLabel(0)).toBe("0 mos");
    expect(experienceLabel(null)).toBeNull();
  });
});
