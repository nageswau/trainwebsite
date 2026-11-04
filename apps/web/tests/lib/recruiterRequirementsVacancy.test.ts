import { describe, expect, it } from "vitest";

import { possibleDuplicate, type Requirement, requirementBody, salaryText, valuesOf } from "@/lib/recruiterRequirements";

// hrc-005 (DEC-SCOPE-381): the §4.2 fields on the form's wire, the pay text and the 409 `possible_duplicate` parser.
const base = {
  title: "Analyst", location: "Pune, MH, India", description: "", skills: [], city: "Pune", state: "MH", country: "India",
  relocation_required: false, salary_currency: "USD", salary_period: "month", hiring_manager: { id: "u9", full_name: "Hema" },
  lead_source: { id: "s1", name: "Referral" }, requisition_reference: "RQ-1", expected_joining_date: "2026-12-01",
} as unknown as Requirement;

describe("hrc-005 vacancy fields", () => {
  it("reads the new fields into the form and sends only the changed ones", () => {
    const values = valuesOf(base);
    expect(values).toMatchObject({ city: "Pune", relocation_required: "no", salary_currency: "USD", hiring_manager_user_id: "u9", lead_source_id: "s1" });
    expect(requirementBody({ ...values, relocation_required: "yes" }, values)).toEqual({ relocation_required: true });
    expect(requirementBody({ ...values, relocation_required: "" }, values)).toEqual({ relocation_required: null });
    expect(requirementBody({ ...values, hiring_manager_user_id: "" }, values)).toEqual({ hiring_manager_user_id: null });
    expect(requirementBody({ ...values, salary_currency: "eur" }, values)).toEqual({ salary_currency: "EUR" });
  });

  it("tolerates a requirement read before the fields existed", () => {
    const values = valuesOf({ title: "Old", location: "Pune", description: "", skills: [] } as unknown as Requirement);
    expect(values.city).toBe("");
    expect(values.relocation_required).toBe("");
  });

  it("names the currency and the pay period", () => {
    expect(salaryText("1000", "2000", "USD", "month")).toBe("USD 1,000 – USD 2,000 a month");
    expect(salaryText("300000", null, "INR", null)).toBe("From ₹3,00,000 a year");
    expect(salaryText("300000", "600000")).toBe("₹3,00,000 – ₹6,00,000 a year");
  });

  it("recognises only the possible-duplicate refusal", () => {
    const detail = { code: "possible_duplicate", message: "m", total: 1, matches: [{ id: "j1", code: "REQ-1", title: "A", location: "Pune", status_label: "Sourcing", requisition_reference: null }] };
    expect(possibleDuplicate(detail)?.matches[0].code).toBe("REQ-1");
    expect(possibleDuplicate({ code: "record_changed" })).toBeNull();
    expect(possibleDuplicate("text")).toBeNull();
  });
});
