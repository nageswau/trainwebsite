import { describe, expect, it } from "vitest";

import { MANAGEMENT_PILLARS } from "@/lib/management";
import { abroadLedgerHref, abroadRevenueUrl, revenueShare } from "@/lib/managementAbroadRevenue";

describe("mgmt-006 Abroad revenue links", () => {
  it("asks the API for the chosen month, or the default month without one", () => {
    expect(abroadRevenueUrl("2026-04")).toBe("/api/v1/management/revenue/abroad?month=2026-04");
    expect(abroadRevenueUrl("")).toBe("/api/v1/management/revenue/abroad");
  });

  it("links to the month's Abroad lines in the ledger, manual and automatic", () => {
    expect(abroadLedgerHref("2026-04")).toBe("/management/ledger?month=2026-04&vertical=abroad&include=auto");
  });

  it("gives a row's share of the annual revenue, 0 when there is no positive revenue, never beyond 0-100", () => {
    expect(revenueShare("25000.00", "100000.00")).toBe(25);
    expect(revenueShare("1.00", "3.00")).toBe(33.3);
    expect(revenueShare("500.00", "0.00")).toBe(0);
    expect(revenueShare("-200.00", "1000.00")).toBe(0);
    expect(revenueShare("1500.00", "1000.00")).toBe(100);
  });

  it("makes the Command Center's Abroad Education revenue entry live for the finance tier", () => {
    const entry = MANAGEMENT_PILLARS.flatMap((p) => p.entries).find((e) => e.item === "mgmt-006");
    expect(entry).toEqual({ label: "Abroad Education revenue", item: "mgmt-006", tier: "finance", href: "/management/revenue/abroad" });
  });
});
