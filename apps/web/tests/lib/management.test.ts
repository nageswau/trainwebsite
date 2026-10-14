import { describe, expect, it } from "vitest";

import { MANAGEMENT_PILLARS, managementNavFor, pillarsFor, type ManagementTiers } from "@/lib/management";
import { dashboardPathFor, ROLE_DASHBOARD_PATH, SUPER_ADMIN_NAV } from "@/lib/navigation";

const PARTNER: ManagementTiers = { operational: true, finance: true, partner_only: true };
const ACCOUNTANT: ManagementTiers = { operational: false, finance: true, partner_only: false };
const SUPER_ADMIN: ManagementTiers = { operational: true, finance: false, partner_only: false };
const HOME = { label: "Command Center", href: "/management" };
const ACTIVITY = { label: "Management activity", href: "/management/activity" };
const SNAPSHOT_LINK = { label: "Business snapshot", href: "/management/snapshot" };

describe("mgmt-001 landing (AC3)", () => {
  it("lands partners and accountants on the Command Center", () => {
    expect(ROLE_DASHBOARD_PATH.partner).toBe("/management");
    expect(ROLE_DASHBOARD_PATH.accountant).toBe("/management");
    expect(dashboardPathFor({ role: "partner", division: "global" })).toBe("/management");
  });

  it("keeps every other landing unchanged (AC5)", () => {
    expect(ROLE_DASHBOARD_PATH.super_admin).toBe("/admin");
    expect(ROLE_DASHBOARD_PATH.partnership_head).toBe("/partnership/head/team");
  });

  it("gives the super admin a Command Center link (MG10)", () => {
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Management Command Center", href: "/management" });
    expect(SUPER_ADMIN_NAV).toContainEqual(ACTIVITY); // mgmt-002
  });
});

describe("mgmt-001 pillars (§33, MG8/MG9)", () => {
  it("holds §33's five pillars and Business Intelligence, in source order", () => {
    expect(MANAGEMENT_PILLARS.map((p) => p.title)).toEqual(["Students", "Sales", "Finance", "People", "Partnerships", "Business Intelligence"]);
  });

  it("names a mgmt item and a tier on every entry; only the landed items are live", () => {
    const entries = MANAGEMENT_PILLARS.flatMap((p) => p.entries);
    expect(entries.every((e) => /^mgmt-\d{3}$/.test(e.item) && ["operational", "finance", "partner_only"].includes(e.tier))).toBe(true);
    expect(entries.filter((e) => e.href).map((e) => e.item)).toContain("mgmt-003");
  });

  it("shows a partner every pillar and entry", () => {
    expect(pillarsFor(PARTNER)).toEqual(MANAGEMENT_PILLARS);
  });

  it("shows an accountant finance entries only -- never investments or capital (M13)", () => {
    const shown = pillarsFor(ACCOUNTANT);
    const labels = shown.flatMap((p) => p.entries.map((e) => e.label));
    expect(shown.flatMap((p) => p.entries).every((e) => e.tier === "finance")).toBe(true);
    expect(labels).toContain("Salaries");
    expect(labels).not.toContain("Investments & ROI");
    expect(labels).not.toContain("Partner capital accounts");
    expect(shown.map((p) => p.title)).not.toContain("Students");
  });

  it("shows the super admin operational entries only -- no finance figures (M13)", () => {
    const entries = pillarsFor(SUPER_ADMIN).flatMap((p) => p.entries);
    expect(entries.length).toBeGreaterThan(0);
    expect(entries.every((e) => e.tier === "operational")).toBe(true);
    expect(pillarsFor(SUPER_ADMIN).map((p) => p.title)).not.toContain("Finance");
  });

  it("puts the Command Center home first, and a live entry only in the sidebars of the tiers that may see it", () => {
    expect(managementNavFor(PARTNER)[0]).toEqual({ label: "Command Center", href: "/management" });
    expect(managementNavFor(PARTNER)).toContainEqual(SNAPSHOT_LINK);
    expect(managementNavFor(ACCOUNTANT)[0]).toEqual({ label: "Command Center", href: "/management" });
    expect(managementNavFor(ACCOUNTANT)).not.toContainEqual(SNAPSHOT_LINK);
    expect(managementNavFor(PARTNER)).toContainEqual(ACTIVITY); // mgmt-002: every tier
    expect(managementNavFor(ACCOUNTANT)).toContainEqual(ACTIVITY);
  });

  it("adds a live entry to the sidebar for the tiers that may see it", () => {
    const live = [{ title: "Finance", entries: [{ label: "Salaries", item: "mgmt-011", tier: "finance" as const, href: "/management/salaries" }] }];
    expect(managementNavFor(ACCOUNTANT, live)).toContainEqual({ label: "Salaries", href: "/management/salaries" });
    expect(managementNavFor(SUPER_ADMIN, live)).toEqual([HOME, ACTIVITY]);
  });
});

describe("mgmt-012 marketing entries (MK14)", () => {
  it("links the finance tier to the ROI page and the super admin to its lead figures", () => {
    const roi = { label: "Marketing budget & ROI", href: "/management/marketing" };
    const leads = { label: "Marketing leads", href: "/management/marketing#marketing-leads" };
    expect(managementNavFor(ACCOUNTANT)).toContainEqual(roi);
    expect(managementNavFor(ACCOUNTANT)).not.toContainEqual(leads);
    expect(managementNavFor(SUPER_ADMIN)).toContainEqual(leads);
    expect(managementNavFor(SUPER_ADMIN)).not.toContainEqual(roi);
  });
});

describe("mgmt-003 business snapshot entry (MS18)", () => {
  it("is the first Business Intelligence entry, live, operational tier", () => {
    const bi = MANAGEMENT_PILLARS.find((p) => p.title === "Business Intelligence")!;
    expect(bi.entries[0]).toEqual({ label: "Business snapshot", item: "mgmt-003", tier: "operational", href: "/management/snapshot" });
  });

  it("reaches the partner and the super admin, never the accountant (M13)", () => {
    const labels = (tiers: ManagementTiers) => pillarsFor(tiers).flatMap((p) => p.entries.map((e) => e.label));
    expect(labels(PARTNER)).toContain("Business snapshot");
    expect(labels(SUPER_ADMIN)).toContain("Business snapshot");
    expect(labels(ACCOUNTANT)).not.toContain("Business snapshot");
  });
});

describe("mgmt-015 partner capital accounts entry (CP15)", () => {
  it("is live in Finance, partner-only (M13)", () => {
    const entry = MANAGEMENT_PILLARS.flatMap((p) => p.entries).find((e) => e.label === "Partner capital accounts");
    expect(entry).toEqual({ label: "Partner capital accounts", item: "mgmt-015", tier: "partner_only", href: "/management/capital" });
    const labels = (tiers: ManagementTiers) => pillarsFor(tiers).flatMap((p) => p.entries.map((e) => e.label));
    expect(labels(PARTNER)).toContain("Partner capital accounts");
    expect(labels(SUPER_ADMIN)).not.toContain("Partner capital accounts");
  });
});
