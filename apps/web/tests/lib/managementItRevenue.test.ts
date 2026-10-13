import { describe, expect, it } from "vitest";

import { MANAGEMENT_PILLARS } from "@/lib/management";
import { itRevenueHref, itRevenuePaymentsUrl, itRevenueQuery, itRevenueUrl } from "@/lib/managementItRevenue";

const COURSE = "0b6f1c2e-6a8f-4f7e-9a51-2a7f3c9d1e00";

describe("mgmt-007 managementItRevenue", () => {
  it("reads the month, period, payments scope and page from the address, dropping malformed values", () => {
    expect(itRevenueQuery({ month: "2026-05", period: "year", program: COURSE, page: "3" })).toEqual({ month: "2026-05", period: "year", scope: { program: COURSE }, page: 3 });
    expect(itRevenueQuery({ batch: COURSE })).toEqual({ month: "", period: "month", scope: { batch: COURSE }, page: 1 });
    expect(itRevenueQuery({ unlinked: "1" }).scope).toEqual({ unlinked: true });
    expect(itRevenueQuery({ month: "2026-5", period: "week", program: "x", page: "-2" })).toEqual({ month: "", period: "month", scope: null, page: 1 });
    expect(itRevenueQuery({ month: ["2026-05", "2026-06"], program: COURSE, batch: COURSE }).scope).toBeNull(); // two scopes: neither
  });

  it("builds the API urls", () => {
    expect(itRevenueUrl({ month: "", period: "month" })).toBe("/api/v1/management/revenue/it");
    expect(itRevenueUrl({ month: "2026-05", period: "year" })).toBe("/api/v1/management/revenue/it?month=2026-05&period=year");
    expect(itRevenuePaymentsUrl({ month: "2026-05", period: "month", scope: { program: COURSE }, page: 2 })).toBe(
      `/api/v1/management/revenue/it/payments?month=2026-05&period=month&program_id=${COURSE}&limit=25&offset=25`,
    );
    expect(itRevenuePaymentsUrl({ month: "", period: "month", scope: { unlinked: true }, page: 1 })).toBe("/api/v1/management/revenue/it/payments?period=month&unlinked=true&limit=25&offset=0");
  });

  it("links a course, batch or the unlinked row to its payments on the same page", () => {
    expect(itRevenueHref({ month: "2026-05", period: "year" }, { batch: COURSE })).toBe(`/management/revenue/it?month=2026-05&period=year&batch=${COURSE}#payments`);
    expect(itRevenueHref({ month: "2026-05", period: "month" }, { unlinked: true }, 2)).toBe("/management/revenue/it?month=2026-05&period=month&unlinked=1&page=2#payments");
  });

  it("makes the Command Center's IT Training revenue entry live for the finance tier", () => {
    const entry = MANAGEMENT_PILLARS.flatMap((p) => p.entries).find((e) => e.item === "mgmt-007");
    expect(entry).toEqual({ label: "IT Training revenue", item: "mgmt-007", tier: "finance", href: "/management/revenue/it" });
  });
});
