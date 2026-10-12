import type { NavItem } from "@/lib/navigation";

// mgmt-001 (Management M13): the tiers GET /management/me returns, and who sees what. The API refuses every tier it does not grant;
// this filter only decides what the page lists.
export type ManagementTier = "operational" | "finance" | "partner_only";
export type ManagementTiers = Record<ManagementTier, boolean>;
export type ManagementMe = { id: string; full_name: string; role: string; tiers: ManagementTiers };
// mgmt-003 (MS16): GET /management/snapshot -- S1-S15 in source order, counted live on `as_of` (the IST date).
export type ManagementKpi = { id: string; key: string; label: string; value: number };
export type ManagementSnapshot = { as_of: string; kpis: ManagementKpi[] };

export const MANAGEMENT_HOME = "/management";
export const MANAGEMENT_ROLE_LABEL: Record<string, string> = { partner: "Partner", accountant: "Accountant", super_admin: "Super Administrator" };

// mgmt-001 (MG8/MG9): the EVID-017 §33 pillars, plus Business Intelligence with §1's Strategy entries, each entry naming the item
// that builds it and its tier. An entry gets its `href` when that item lands; until then it is listed as coming soon, never linked.
// Mixed pages (health score, this-month performance, monthly review) stay partner-only until their own item decides.
export type ManagementEntry = { label: string; item: string; tier: ManagementTier; href?: string };
export type ManagementPillar = { title: string; entries: ManagementEntry[] };

const op = (label: string, item: string): ManagementEntry => ({ label, item, tier: "operational" });
const fin = (label: string, item: string): ManagementEntry => ({ label, item, tier: "finance" });
const own = (label: string, item: string): ManagementEntry => ({ label, item, tier: "partner_only" });

export const MANAGEMENT_PILLARS: ManagementPillar[] = [
  { title: "Students", entries: [op("Student funnel", "mgmt-016"), op("Training", "mgmt-017"), op("Counseling", "mgmt-018"), op("Applications", "mgmt-024"), op("Recruitment", "mgmt-025")] },
  { title: "Sales", entries: [op("BDM", "mgmt-020"), op("Leads & calls", "mgmt-019"), fin("Marketing budget & ROI", "mgmt-012")] },
  {
    title: "Finance",
    entries: [
      fin("Ledger", "mgmt-004"), fin("Abroad Education revenue", "mgmt-006"), fin("IT Training revenue", "mgmt-007"), fin("Recruitment revenue", "mgmt-008"),
      fin("Expenses & rent", "mgmt-010"), fin("Profit & loss", "mgmt-009"), fin("Salaries", "mgmt-011"), fin("Accounts", "mgmt-013"),
      own("Investments & ROI", "mgmt-014"), own("Partner capital accounts", "mgmt-015"),
    ],
  },
  { title: "People", entries: [op("Trainers", "mgmt-017"), op("Counselors", "mgmt-018"), op("Telecallers", "mgmt-019"), op("Recruiters", "mgmt-025"), fin("Employee cost", "mgmt-011")] },
  { title: "Partnerships", entries: [op("Agents", "mgmt-021"), op("Schools", "mgmt-022"), op("Universities", "mgmt-023"), op("Companies", "mgmt-025")] },
  {
    title: "Business Intelligence",
    entries: [
      { ...op("Business snapshot", "mgmt-003"), href: "/management/snapshot" },
      own("This month's performance", "mgmt-031"), op("Next month plan & targets", "mgmt-026"), op("Long-term strategy", "mgmt-026"),
      op("Discussions & decisions", "mgmt-027"), op("To-do", "mgmt-028"), op("Meetings", "mgmt-029"), own("Business health score", "mgmt-030"),
      own("Monthly business review", "mgmt-032"),
    ],
  },
];

/** The pillars and entries a caller's tiers allow; a pillar with nothing left is dropped. */
export function pillarsFor(tiers: ManagementTiers, pillars: ManagementPillar[] = MANAGEMENT_PILLARS): ManagementPillar[] {
  return pillars
    .map((pillar) => ({ ...pillar, entries: pillar.entries.filter((entry) => tiers[entry.tier]) }))
    .filter((pillar) => pillar.entries.length > 0);
}

/** The sidebar: the Command Center home, then each live entry the tiers allow. */
export function managementNavFor(tiers: ManagementTiers, pillars: ManagementPillar[] = MANAGEMENT_PILLARS): NavItem[] {
  const live = pillarsFor(tiers, pillars).flatMap((pillar) => pillar.entries.flatMap((entry) => (entry.href ? [{ label: entry.label, href: entry.href }] : [])));
  return [{ label: "Command Center", href: MANAGEMENT_HOME }, ...live];
}
