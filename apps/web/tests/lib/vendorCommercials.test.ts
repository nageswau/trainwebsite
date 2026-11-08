import { describe, expect, it } from "vitest";

import { revenueConflict } from "@/lib/recruiterRevenue";
import { billActionUrl, hoursText, isVendorBillList, isVendorPerformanceDetail, performancePageUrl, rateText, vendorBillsUrl, vendorPerformancePath } from "@/lib/vendorCommercials";

// pob-012 (DEC-SCOPE-433)
describe("vendor commercials helpers", () => {
  it("shows a missing rate or response time as a dash, never 0%", () => {
    expect(rateText(null)).toBe("—");
    expect(rateText("75.0")).toBe("75.0%");
    expect(rateText("0.0")).toBe("0.0%");
    expect(hoursText(null)).toBe("—");
    expect(hoursText("6.0")).toBe("6.0 h");
  });

  it("builds encoded URLs", () => {
    expect(vendorBillsUrl("a/b")).toBe("/api/v1/recruiter/companies/a%2Fb/vendor-bills");
    expect(billActionUrl("x", "payments")).toBe("/api/v1/recruiter/vendor-bills/x/payments");
    expect(vendorPerformancePath("v1")).toBe("/recruiter/vendors/v1/performance");
    expect(performancePageUrl(50)).toBe("/api/v1/recruiter/vendors/performance?limit=50&offset=50");
  });

  it("recognises the payloads and the coded bill conflicts", () => {
    expect(isVendorBillList({ items: [], totals: {}, can_edit: false })).toBe(true);
    expect(isVendorBillList({ items: [] })).toBe(false);
    expect(isVendorPerformanceDetail({ metrics: {}, requirements: [], submissions: [] })).toBe(true);
    expect(revenueConflict({ code: "bill_number_taken", message: "Taken" })).toBe("Taken");
    expect(revenueConflict({ code: "other", message: "x" })).toBeNull();
  });
});
