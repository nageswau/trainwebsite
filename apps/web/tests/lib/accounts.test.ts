import { describe, expect, it } from "vitest";

import { accountsHref, accountsUrl, amountText, balancesBody, balancesUrl, fieldErrors } from "@/lib/accounts";

describe("accounts lib (mgmt-013)", () => {
  it("builds the page and API links, with no month meaning the current month", () => {
    expect(accountsHref("2026-09")).toBe("/management/accounts?month=2026-09");
    expect(accountsUrl("2026-09")).toBe("/api/v1/management/accounts?month=2026-09");
    expect(accountsUrl("")).toBe("/api/v1/management/accounts");
    expect(balancesUrl("2026-09")).toBe("/api/v1/management/accounts/balances?month=2026-09");
  });

  it("shows a figure that was never entered as 'Not entered', never ₹0 (AD9)", () => {
    expect(amountText(null)).toBe("Not entered");
    expect(amountText("0.00")).toBe("₹0.00");
    expect(amountText("-2500.50")).toBe("-₹2,500.50");
    expect(amountText("1850000.00")).toBe("₹18,50,000.00");
  });

  it("sends a blank field as null and anything typed as written, so the API's 422 names it", () => {
    expect(balancesBody({ cash_bank: " 1200.50 ", payables: "", tax_liabilities: "abc" })).toEqual({ cash_bank: "1200.50", payables: null, tax_liabilities: "abc" });
  });

  it("places 422 items on their fields and ignores anything else", () => {
    const detail = [
      { loc: ["body", "payables"], msg: "An amount can't be negative" },
      { loc: ["query", "month"], msg: "Accounts can be shown up to the current month" },
    ];
    expect(fieldErrors(detail)).toEqual({ payables: "An amount can't be negative" });
    expect(fieldErrors("Finance access required")).toEqual({});
  });
});
