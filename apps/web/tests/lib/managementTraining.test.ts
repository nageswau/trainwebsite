import { describe, expect, it } from "vitest";

import { MANAGEMENT_PILLARS, managementNavFor } from "@/lib/management";
import { trainingQuery, trainingUrl } from "@/lib/managementTraining";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

describe("mgmt-017 managementTraining", () => {
  it("reads the period from the address, dropping malformed or repeated values", () => {
    expect(trainingQuery({ from: "2026-05-01", to: "2026-05-31" })).toEqual({ from: "2026-05-01", to: "2026-05-31" });
    expect(trainingQuery({ from: "2026-02-30", to: "31-05-2026" })).toEqual({ from: "", to: "" });
    expect(trainingQuery({ from: ["2026-05-01", "2026-05-02"] })).toEqual({ from: "", to: "" });
  });

  it("builds the API url with only the values set", () => {
    expect(trainingUrl({ from: "", to: "" })).toBe("/api/v1/management/training");
    expect(trainingUrl({ from: "2026-05-01", to: "" })).toBe("/api/v1/management/training?from=2026-05-01");
    expect(trainingUrl({ from: "2026-05-01", to: "2026-05-31" })).toBe("/api/v1/management/training?from=2026-05-01&to=2026-05-31");
  });

  it("makes the Training and Trainers entries live for the operational tier, and links the super admin's sidebar (TR16)", () => {
    const entry = (pillar: string, label: string) => MANAGEMENT_PILLARS.find((p) => p.title === pillar)!.entries.find((e) => e.label === label);
    expect(entry("Students", "Training")).toEqual({ label: "Training", item: "mgmt-017", tier: "operational", href: "/management/training" });
    expect(entry("People", "Trainers")).toEqual({ label: "Trainers", item: "mgmt-017", tier: "operational", href: "/management/training#trainers" });
    expect(managementNavFor({ operational: true, finance: true, partner_only: true })).toContainEqual({ label: "Training", href: "/management/training" });
    expect(managementNavFor({ operational: false, finance: true, partner_only: false })).not.toContainEqual({ label: "Training", href: "/management/training" });
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Management training figures", href: "/management/training" });
  });
});
