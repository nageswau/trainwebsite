import { describe, expect, it } from "vitest";

import { counselingPayload, counselingUrl, counselingValues, CURRENCIES, formatBudget, validateCounseling, type Counseling } from "@/lib/agentStudents";

const record: Counseling = {
  counseling_completed: true, completed_at: "2026-10-01T09:00:00Z", completed_by: "Priya", career_interest: "Data science",
  course_preference: null, country_preference: "Ireland", budget_amount: "2500000.00", budget_currency: "USD", remarks: null,
  updated_at: "2026-10-01T09:00:00Z", updated_by: "Priya",
};

describe("counseling helpers (AGN-006)", () => {
  it("builds the sub-resource URL and lists the seven currencies", () => {
    expect(counselingUrl("s1")).toBe("/api/v1/workflows/overseas/agent/crm/students/s1/counseling");
    expect(CURRENCIES).toEqual(["INR", "USD", "GBP", "EUR", "CAD", "AUD", "NZD"]);
  });

  it("starts empty with INR when nothing is recorded, and from the record otherwise", () => {
    expect(counselingValues(null)).toEqual({ counseling_completed: false, career_interest: "", course_preference: "", country_preference: "", budget_amount: "", budget_currency: "INR", remarks: "" });
    expect(counselingValues(record)).toMatchObject({ counseling_completed: true, career_interest: "Data science", course_preference: "", budget_amount: "2500000.00", budget_currency: "USD" });
  });

  it("sends the whole record: trimmed text, blanks as null, amount as a string without grouping, currency only with an amount", () => {
    const values = { ...counselingValues(null), career_interest: "  Law ", budget_amount: "25,00,000", remarks: "  " };
    expect(counselingPayload(values)).toEqual({
      counseling_completed: false, career_interest: "Law", course_preference: null, country_preference: null,
      budget_amount: "2500000", budget_currency: "INR", remarks: null,
    });
    expect(counselingPayload({ ...values, budget_amount: "", budget_currency: "GBP" })).toMatchObject({ budget_amount: null, budget_currency: null });
  });

  it("refuses a negative, too large or too precise amount and over-long text", () => {
    const base = counselingValues(null);
    expect(validateCounseling({ ...base, budget_amount: "-5" })).toEqual({ budget_amount: "Budget cannot be negative" });
    expect(validateCounseling({ ...base, budget_amount: "100000000" }).budget_amount).toMatch(/up to 99,999,999.99/);
    expect(validateCounseling({ ...base, budget_amount: "10.123" }).budget_amount).toMatch(/at most 2 decimals/);
    expect(validateCounseling({ ...base, budget_amount: "abc" }).budget_amount).toBeTruthy();
    expect(validateCounseling({ ...base, country_preference: "x".repeat(121) })).toEqual({ country_preference: "Must be 120 characters or fewer" });
    expect(validateCounseling({ ...base, remarks: "x".repeat(2001) }).remarks).toBe("Must be 2000 characters or fewer");
    expect(validateCounseling({ ...base, budget_amount: "99,999,999.99" })).toEqual({});
  });

  it("refuses a decimal comma instead of saving a multiplied amount, but accepts Indian and Western grouping (review #1)", () => {
    const base = counselingValues(null);
    for (const typed of ["1500,50", "12,5", "1,50", "2,5000"]) {
      expect(validateCounseling({ ...base, budget_amount: typed }).budget_amount).toBe("Use a full stop for decimals (1500.50); commas only group digits");
    }
    for (const typed of ["25,00,000", "2,500,000", "2 500 000", "1,000.50", "99,999,999.99"]) {
      expect(validateCounseling({ ...base, budget_amount: typed })).toEqual({});
    }
  });

  it("formats a budget in its currency", () => {
    expect(formatBudget("2500000.00", "INR")).toBe("₹25,00,000.00");
    expect(formatBudget("1500.50", "USD")).toBe("US$1,500.50");
    expect(formatBudget(null, null)).toBe("—");
  });
});
