import { describe, expect, it } from "vitest";

import { MANAGEMENT_PILLARS, managementNavFor } from "@/lib/management";
import { universitiesHref, universitiesQuery, universitiesUrl } from "@/lib/managementUniversities";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

describe("mgmt-023 managementUniversities", () => {
  it("reads the period from the address, dropping malformed or repeated values", () => {
    expect(universitiesQuery({ from: "2026-05-01", to: "2026-05-31" })).toEqual({ from: "2026-05-01", to: "2026-05-31" });
    expect(universitiesQuery({ from: "2026-02-30", to: "31-05-2026" })).toEqual({ from: "", to: "" });
    expect(universitiesQuery({ from: ["2026-05-01", "2026-05-02"] })).toEqual({ from: "", to: "" });
  });

  it("builds the API url and the page address with only the values set", () => {
    expect(universitiesUrl({ from: "", to: "" })).toBe("/api/v1/management/universities");
    expect(universitiesUrl({ from: "2026-05-01", to: "" })).toBe("/api/v1/management/universities?from=2026-05-01");
    expect(universitiesHref({ from: "2026-05-01", to: "2026-05-31" })).toBe("/management/universities?from=2026-05-01&to=2026-05-31");
    expect(universitiesHref({ from: "", to: "" })).toBe("/management/universities");
  });

  it("makes the Universities entry live for the operational tier, and links the super admin's sidebar (UD14)", () => {
    const entry = MANAGEMENT_PILLARS.find((p) => p.title === "Partnerships")!.entries.find((e) => e.label === "Universities");
    expect(entry).toEqual({ label: "Universities", item: "mgmt-023", tier: "operational", href: "/management/universities" });
    expect(managementNavFor({ operational: true, finance: true, partner_only: true })).toContainEqual({ label: "Universities", href: "/management/universities" });
    expect(managementNavFor({ operational: false, finance: true, partner_only: false })).not.toContainEqual({ label: "Universities", href: "/management/universities" });
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Management university figures", href: "/management/universities" });
  });
});
