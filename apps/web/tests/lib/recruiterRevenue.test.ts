import { describe, expect, it } from "vitest";

import { feeSourceText, inr, invoicesUrl, isReceivableView, revenueConflict } from "@/lib/recruiterRevenue";

// rec-031 (DEC-SCOPE-175): the revenue helpers -- Indian-grouped rupees, where the fee per hire comes from, the coded 409s, the list URL.
describe("recruiterRevenue helpers (rec-031)", () => {
  it("formats rupees with Indian grouping and always two decimals", () => {
    expect(inr("150000.00")).toBe("₹1,50,000.00");
    expect(inr("50000")).toBe("₹50,000.00");
    expect(inr("0.00")).toBe("₹0.00");
    expect(inr("1234567.5")).toBe("₹12,34,567.50");
    expect(inr(null)).toBe("—");
  });

  it("says where the fee per hire comes from (RV1)", () => {
    const fee = { basis: "fixed" as const, value: "50000.00", override: null };
    expect(feeSourceText({ ...fee, source: "contract", contract_status_label: "Signed" })).toBe("₹50,000 per hire · from the company contract (Signed)");
    expect(feeSourceText({ ...fee, source: "requirement", contract_status_label: null, override: { basis: "fixed", value: "50000.00" } })).toBe("₹50,000 per hire · set for this requirement");
    expect(feeSourceText({ basis: "percent_of_ctc", value: "8.33", source: "contract", contract_status_label: "Active", override: null })).toBe("8.33% of CTC · from the company contract (Active)");
    expect(feeSourceText({ basis: null, value: null, source: null, contract_status_label: null, override: null })).toBe("No fee set");
  });

  it("reads the coded 409s and nothing else", () => {
    expect(revenueConflict({ message: "This invoice number is already used", code: "invoice_number_taken" })).toBe("This invoice number is already used");
    expect(revenueConflict({ message: "This invoice is cancelled", code: "invoice_cancelled" })).toBe("This invoice is cancelled");
    expect(revenueConflict({ message: "x", code: "other" })).toBeNull();
    expect(revenueConflict("Not found")).toBeNull();
  });

  it("builds the receivables URL and knows its views", () => {
    expect(invoicesUrl("overdue", 50)).toBe("/api/v1/recruiter/invoices?view=overdue&limit=50&offset=50");
    expect(invoicesUrl("outstanding", 0, "C1")).toBe("/api/v1/recruiter/invoices?view=outstanding&limit=50&offset=0&company_id=C1");
    expect(isReceivableView("paid")).toBe(true);
    expect(isReceivableView("everything")).toBe(false);
  });
});
