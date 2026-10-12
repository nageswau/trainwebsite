import { describe, expect, it } from "vitest";

import {
  EMPTY_INVESTMENT_FORM,
  investmentBody,
  investmentFilters,
  investmentFormFrom,
  investmentProblem,
  investmentsHref,
  investmentsUrl,
  investmentUrl,
  roiText,
  rupees,
  type Investment,
} from "@/lib/investments";
import { MANAGEMENT_PILLARS, managementNavFor } from "@/lib/management";

const SAMPLE: Investment = {
  id: "11111111-1111-1111-1111-111111111111", code: "INV-000001", invested_on: "2026-04-01", investor_kind: "partner",
  investor: { id: "22222222-2222-2222-2222-222222222222", full_name: "Meera Partner" }, amount: "500000.00", purpose: "Marketing Campaign",
  vertical: "shared", expected_return: "1500000.00", actual_return: null, roi: null, status: "active", notes: null,
  created_by: { id: "x", full_name: "A" }, updated_by: { id: "x", full_name: "A" }, created_at: "2026-04-01T10:00:00Z", updated_at: "2026-04-01T10:00:00Z",
};

describe("mgmt-014 money and ROI text (MI6, MI7)", () => {
  it("writes rupees the Indian way", () => {
    expect(rupees("500000.00")).toBe("₹5,00,000.00");
    expect(rupees("1800000")).toBe("₹18,00,000.00");
    expect(rupees(null)).toBe("—");
  });

  it("shows the source example as 260% and an unknown ROI as a dash (AC1, edge case)", () => {
    expect(roiText("260.00")).toBe("260.00%");
    expect(roiText("-66.67")).toBe("-66.67%");
    expect(roiText(null)).toBe("—");
  });
});

describe("mgmt-014 register filters and URLs (MI9)", () => {
  it("keeps known filters and drops anything else", () => {
    expect(investmentFilters({ date_from: "2026-04-01", date_to: "2026-13-01", vertical: "it", status: "lost", offset: "25", x: "1" })).toEqual({
      date_from: "2026-04-01", date_to: "", vertical: "it", status: "", offset: 25,
    });
    expect(investmentFilters({ vertical: ["it", "abroad"], offset: "-3" })).toEqual({ date_from: "", date_to: "", vertical: "", status: "", offset: 0 });
    // Browser QA-01: past the API's 10 000 cap the API answered with a list 422, shown as "[object Object]".
    expect(investmentFilters({ offset: "999999" }).offset).toBe(10_000);
  });

  it("builds the page link and the API URL", () => {
    const filters = { date_from: "2026-04-01", date_to: "", vertical: "it", status: "", offset: 0 };
    expect(investmentsHref(filters)).toBe("/management/investments?date_from=2026-04-01&vertical=it");
    expect(investmentsHref({ ...filters, date_from: "", vertical: "" })).toBe("/management/investments");
    expect(investmentsUrl({ ...filters, offset: 25 })).toBe("/api/v1/management/investments?date_from=2026-04-01&vertical=it&offset=25&limit=25");
    expect(investmentUrl("abc")).toBe("/api/v1/management/investments/abc");
  });
});

describe("mgmt-014 form (MI2, MI4, MI6)", () => {
  const valid = { ...EMPTY_INVESTMENT_FORM, invested_on: "2026-04-01", amount: "500000", purpose: "Marketing Campaign", vertical: "shared" };

  it("names the first problem, field by field", () => {
    expect(investmentProblem({ ...valid, invested_on: "" })).toEqual({ field: "invested_on", message: "Enter the investment date." });
    expect(investmentProblem({ ...valid, investor_kind: "partner" })).toEqual({ field: "investor_user_id", message: "Choose the partner who invested." });
    expect(investmentProblem({ ...valid, amount: "0" })).toEqual({ field: "amount", message: "The amount must be more than ₹0." });
    expect(investmentProblem({ ...valid, amount: "1.234" })).toEqual({ field: "amount", message: "Enter the amount in rupees with up to 2 decimals." });
    expect(investmentProblem({ ...valid, expected_return: "-5" })).toEqual({ field: "expected_return", message: "Enter the expected return in rupees with up to 2 decimals." });
    expect(investmentProblem({ ...valid, purpose: " x " })).toEqual({ field: "purpose", message: "Enter the purpose (at least 2 characters)." });
    expect(investmentProblem({ ...valid, vertical: "" })).toEqual({ field: "vertical", message: "Choose the business vertical." });
    expect(investmentProblem(valid)).toBeNull();
  });

  it("sends trimmed values, nulls for blanks, and no partner for a company investment", () => {
    expect(investmentBody({ ...valid, investor_user_id: "abc", notes: "  hi \n", expected_return: "" })).toEqual({
      invested_on: "2026-04-01", investor_kind: "company", investor_user_id: null, amount: "500000", purpose: "Marketing Campaign", vertical: "shared",
      expected_return: null, actual_return: null, status: "active", notes: "hi",
    });
  });

  it("fills the edit form from an investment", () => {
    expect(investmentFormFrom(SAMPLE)).toEqual({
      invested_on: "2026-04-01", investor_kind: "partner", investor_user_id: "22222222-2222-2222-2222-222222222222", amount: "500000.00",
      purpose: "Marketing Campaign", vertical: "shared", expected_return: "1500000.00", actual_return: "", status: "active", notes: "",
    });
  });
});

describe("mgmt-014 Command Center entry (MI13)", () => {
  it("is live, partner-only, and in the partner's sidebar only", () => {
    const entry = MANAGEMENT_PILLARS.flatMap((p) => p.entries).find((e) => e.item === "mgmt-014");
    expect(entry).toEqual({ label: "Investments & ROI", item: "mgmt-014", tier: "partner_only", href: "/management/investments" });
    const link = { label: "Investments & ROI", href: "/management/investments" };
    expect(managementNavFor({ operational: true, finance: true, partner_only: true })).toContainEqual(link);
    expect(managementNavFor({ operational: false, finance: true, partner_only: false })).not.toContainEqual(link);
    expect(managementNavFor({ operational: true, finance: false, partner_only: false })).not.toContainEqual(link);
  });
});
