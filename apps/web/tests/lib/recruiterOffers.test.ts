import { describe, expect, it } from "vitest";

import { isApplicationOffer, offerEventText, offerOf, OFFER_STATUS_LABELS, offerUrl, salaryText, studentLetterUrl } from "@/lib/recruiterOffers";
import { recOffer } from "@/tests/helpers/recruiterOffers";

// rec-022 (DEC-SCOPE-152): the §16 labels, the endpoints, the reply guards, the salary and history wording.
describe("recruiterOffers", () => {
  it("labels the four §16 statuses in source order", () => {
    expect(Object.values(OFFER_STATUS_LABELS)).toEqual(["Offer Pending", "Offer Received", "Accepted", "Declined"]);
  });

  it("builds encoded endpoints", () => {
    expect(offerUrl("a/b", "letter")).toBe("/api/v1/recruiter/offers/a%2Fb/letter");
    expect(offerUrl("O1")).toBe("/api/v1/recruiter/offers/O1");
    expect(studentLetterUrl("O1")).toBe("/api/v1/workflows/it/student/offers/O1/letter");
  });

  it("guards the replies", () => {
    expect(offerOf({ offer: recOffer() })?.id).toBe("O1");
    expect(offerOf({ offer: { id: "x" } })).toBeNull();
    expect(isApplicationOffer({ offer: null, can_create: true })).toBe(true);
    expect(isApplicationOffer({ offer: { id: "x" }, can_create: false })).toBe(false);
  });

  it("formats the salary with Indian grouping for INR", () => {
    expect(salaryText("600000.00", "INR")).toBe("INR 6,00,000.00");
    expect(salaryText(1250, "USD")).toBe("USD 1,250.00");
    expect(salaryText(null, "INR")).toBeNull();
  });

  it("words each history row without values", () => {
    const actor = { id: "r1", full_name: "Riya" };
    const base = { from_status: null, to_status: "offer_pending", fields: null, note: null, actor, created_at: "" };
    expect(offerEventText({ ...base, event: "created" }, "today")).toBe("Recorded as Offer Pending today by Riya");
    expect(offerEventText({ ...base, event: "revised", fields: ["compensation", "position"] }, "today")).toBe("Revised (Salary, Position) today by Riya");
    expect(offerEventText({ ...base, event: "status", from_status: "offer_pending", to_status: "accepted", note: "Signed" }, "today"))
      .toBe("Offer Pending → Accepted today by Riya — Signed");
    expect(offerEventText({ ...base, event: "letter", actor: null }, "today")).toBe("Offer letter uploaded today");
  });
});
