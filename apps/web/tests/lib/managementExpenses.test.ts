import { describe, expect, it } from "vitest";

import { MANAGEMENT_PILLARS } from "@/lib/management";
import { expenseMonth, expensesLedgerHref, expensesUrl, formatMonth, istMonth } from "@/lib/managementExpenses";

describe("mgmt-010 expense dashboard links", () => {
  it("keeps a well-formed month and drops anything else from the address", () => {
    expect(expenseMonth({ month: "2026-04" })).toBe("2026-04");
    expect(expenseMonth({ month: "2026-13" })).toBe("");
    expect(expenseMonth({ month: "2026-4" })).toBe("");
    expect(expenseMonth({ month: ["2026-04", "2026-05"] })).toBe("");
    expect(expenseMonth({})).toBe("");
  });

  it("asks the API for the chosen month, or the default month without one", () => {
    expect(expensesUrl("2026-04")).toBe("/api/v1/management/expenses?month=2026-04");
    expect(expensesUrl("")).toBe("/api/v1/management/expenses");
  });

  it("links to the month's expense lines in the ledger, manual and automatic", () => {
    expect(expensesLedgerHref("2026-04")).toBe("/management/ledger?month=2026-04&kind=expense&include=auto");
  });

  it("names a month in words and finds the IST month of a moment", () => {
    expect(formatMonth("2026-04")).toBe("April 2026");
    expect(istMonth(new Date("2026-09-30T19:00:00Z"))).toBe("2026-10"); // 00:30 on 1 October in India
    expect(istMonth(new Date("2026-09-30T18:00:00Z"))).toBe("2026-09");
  });

  it("makes the Command Center's Expenses entry live for the finance tier", () => {
    const entry = MANAGEMENT_PILLARS.flatMap((p) => p.entries).find((e) => e.item === "mgmt-010");
    expect(entry).toEqual({ label: "Expenses & rent", item: "mgmt-010", tier: "finance", href: "/management/expenses" });
  });
});
