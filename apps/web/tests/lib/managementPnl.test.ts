import { describe, expect, it } from "vitest";

import { MANAGEMENT_PILLARS } from "@/lib/management";
import { formatMargin, isLoss, pnlQuery, pnlUrl } from "@/lib/managementPnl";

describe("mgmt-009 managementPnl", () => {
  it("reads the month and period from the address, dropping malformed values", () => {
    expect(pnlQuery({ month: "2026-05", period: "quarter" })).toEqual({ month: "2026-05", period: "quarter" });
    expect(pnlQuery({ period: "year" })).toEqual({ month: "", period: "year" });
    expect(pnlQuery({ month: "2026-5", period: "week" })).toEqual({ month: "", period: "month" });
    expect(pnlQuery({ month: ["2026-05", "2026-06"], period: ["year"] })).toEqual({ month: "", period: "month" });
  });

  it("builds the API url, leaving the defaults to the API", () => {
    expect(pnlUrl({ month: "", period: "month" })).toBe("/api/v1/management/pnl");
    expect(pnlUrl({ month: "2026-05", period: "month" })).toBe("/api/v1/management/pnl?month=2026-05&period=month");
    expect(pnlUrl({ month: "", period: "quarter" })).toBe("/api/v1/management/pnl?period=quarter");
  });

  it("formats a margin and tells a loss", () => {
    expect(formatMargin(37.5)).toBe("37.5%");
    expect(formatMargin(-12)).toBe("-12.0%");
    expect(formatMargin(null)).toBe("—");
    expect(isLoss("-0.01")).toBe(true);
    expect(isLoss("0.00")).toBe(false);
    expect(isLoss("15.00")).toBe(false);
  });

  it("makes the Command Center's Profit & loss entry live for the finance tier", () => {
    const entry = MANAGEMENT_PILLARS.flatMap((p) => p.entries).find((e) => e.item === "mgmt-009");
    expect(entry).toEqual({ label: "Profit & loss", item: "mgmt-009", tier: "finance", href: "/management/pnl" });
  });
});
