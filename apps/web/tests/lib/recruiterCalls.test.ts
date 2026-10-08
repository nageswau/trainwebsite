import { describe, expect, it } from "vitest";

import { isLogCallResult, isRecCall, partyCallsUrl, telHref } from "@/lib/recruiterCalls";

describe("recruiterCalls (rec-025)", () => {
  it("builds a tel: link from a typed phone", () => {
    expect(telHref("+91 98765 43210")).toBe("tel:+919876543210");
    expect(telHref("(020) 4567-8900")).toBe("tel:02045678900");
    expect(telHref("  ")).toBeNull();
    expect(telHref(null)).toBeNull();
    expect(telHref("ext 12")).toBeNull();
    expect(telHref("javascript:alert(1)//123456")).toBe("tel:1123456");
  });

  it("builds the party's list URL", () => {
    expect(partyCallsUrl({ kind: "contact", companyId: "C 1" })).toBe("/api/v1/recruiter/companies/C%201/calls?limit=50");
    expect(partyCallsUrl({ kind: "candidate", candidateId: "K1" })).toBe("/api/v1/recruiter/candidates/K1/calls?limit=50");
  });

  it("guards the call shapes", () => {
    const call = { id: "1", occurred_at: "2026-10-08T05:00:00Z", outcome: "busy", can_change: false };
    expect(isRecCall(call)).toBe(true);
    expect(isRecCall({ id: "1" })).toBe(false);
    expect(isLogCallResult({ call, follow_up_id: null })).toBe(true);
    expect(isLogCallResult({ call })).toBe(false);
  });
});
