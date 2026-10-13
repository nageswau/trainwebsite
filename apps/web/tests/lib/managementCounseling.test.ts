import { describe, expect, it } from "vitest";

import { MANAGEMENT_PILLARS, managementNavFor } from "@/lib/management";
import { counselingQuery, counselingUrl, formatCount, formatPct } from "@/lib/managementCounseling";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

describe("mgmt-018 managementCounseling", () => {
  it("reads the period from the address, dropping malformed or repeated values", () => {
    expect(counselingQuery({ from: "2026-05-01", to: "2026-05-31" })).toEqual({ from: "2026-05-01", to: "2026-05-31" });
    expect(counselingQuery({ from: "2026-02-30", to: "31-05-2026" })).toEqual({ from: "", to: "" });
    expect(counselingQuery({ from: ["2026-05-01", "2026-05-02"] })).toEqual({ from: "", to: "" });
  });

  it("builds the API url with only the values set", () => {
    expect(counselingUrl({ from: "", to: "" })).toBe("/api/v1/management/counseling");
    expect(counselingUrl({ from: "2026-05-01", to: "2026-05-31" })).toBe("/api/v1/management/counseling?from=2026-05-01&to=2026-05-31");
  });

  it("formats counts with Indian grouping and the conversion share to one decimal", () => {
    expect(formatCount(150000)).toBe("1,50,000");
    expect(formatPct(33.3)).toBe("33.3%");
    expect(formatPct(100)).toBe("100.0%");
  });

  it("makes the Counseling and Counselors entries live for the operational tier, and links the super admin's sidebar (CS12)", () => {
    const entry = (pillar: string, label: string) => MANAGEMENT_PILLARS.find((p) => p.title === pillar)!.entries.find((e) => e.label === label);
    expect(entry("Students", "Counseling")).toEqual({ label: "Counseling", item: "mgmt-018", tier: "operational", href: "/management/counseling" });
    expect(entry("People", "Counselors")).toEqual({ label: "Counselors", item: "mgmt-018", tier: "operational", href: "/management/counseling#counselors" });
    expect(managementNavFor({ operational: true, finance: true, partner_only: true })).toContainEqual({ label: "Counseling", href: "/management/counseling" });
    expect(managementNavFor({ operational: false, finance: true, partner_only: false })).not.toContainEqual({ label: "Counseling", href: "/management/counseling" });
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Management counseling figures", href: "/management/counseling" });
  });
});
