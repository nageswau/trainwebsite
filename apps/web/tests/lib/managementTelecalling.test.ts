import { describe, expect, it } from "vitest";

import { MANAGEMENT_PILLARS, managementNavFor } from "@/lib/management";
import { conversionText, stepShareText, telecallingFilters, telecallingHref, telecallingUrl } from "@/lib/managementTelecalling";

describe("mgmt-019 telecalling helpers", () => {
  it("keeps only well-formed single dates from the address", () => {
    expect(telecallingFilters({ date_from: "2026-10-01", date_to: "2026-10-13" })).toEqual({ date_from: "2026-10-01", date_to: "2026-10-13" });
    expect(telecallingFilters({ date_from: "2026-02-30", date_to: ["2026-10-01", "2026-10-02"] })).toEqual({ date_from: "", date_to: "" });
    expect(telecallingFilters({})).toEqual({ date_from: "", date_to: "" });
  });

  it("builds the API and page addresses with only the set dates", () => {
    expect(telecallingUrl({ date_from: "", date_to: "" })).toBe("/api/v1/management/telecalling");
    expect(telecallingUrl({ date_from: "2026-10-01", date_to: "" })).toBe("/api/v1/management/telecalling?date_from=2026-10-01");
    expect(telecallingHref({ date_from: "2026-10-01", date_to: "2026-10-13" })).toBe("/management/telecalling?date_from=2026-10-01&date_to=2026-10-13");
  });

  it("words conversion and step shares, with a dash when there is nothing to divide by", () => {
    expect(conversionText(12.5)).toBe("12.5%");
    expect(conversionText(null)).toBe("—");
    expect(stepShareText(40)).toBe("40% of calls");
    expect(stepShareText(null)).toBeNull();
  });

  it("makes both mgmt-019 Command Center entries live for the operational tier only", () => {
    const entries = MANAGEMENT_PILLARS.flatMap((pillar) => pillar.entries).filter((entry) => entry.item === "mgmt-019");
    expect(entries.map((entry) => [entry.label, entry.href])).toEqual([
      ["Leads & calls", "/management/telecalling"],
      ["Telecallers", "/management/telecalling#telecallers"],
    ]);
    const operational = managementNavFor({ operational: true, finance: false, partner_only: false });
    expect(operational).toContainEqual({ label: "Leads & calls", href: "/management/telecalling" });
    const finance = managementNavFor({ operational: false, finance: true, partner_only: false });
    expect(finance.some((item) => item.href.startsWith("/management/telecalling"))).toBe(false);
  });
});
