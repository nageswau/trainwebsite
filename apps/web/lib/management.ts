import { isCalendarDate } from "@/lib/formatDate";
import { MANAGEMENT_TASKS_NAV, type NavItem } from "@/lib/navigation";

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
  { title: "Students", entries: [{ ...op("Student funnel", "mgmt-016"), href: "/management/funnel" }, { ...op("Training", "mgmt-017"), href: "/management/training" }, { ...op("Counseling", "mgmt-018"), href: "/management/counseling" }, { ...op("Applications", "mgmt-024"), href: "/management/applications" }, { ...op("Recruitment", "mgmt-025"), href: "/management/recruitment" }] },
  { title: "Sales", entries: [{ ...op("BDM", "mgmt-020"), href: "/management/bdm" }, { ...op("Leads & calls", "mgmt-019"), href: "/management/telecalling" }, { ...fin("Marketing budget & ROI", "mgmt-012"), href: "/management/marketing" }, { ...op("Marketing leads", "mgmt-012"), href: "/management/marketing#marketing-leads" }] },
  {
    title: "Finance",
    entries: [
      { ...fin("Ledger", "mgmt-004"), href: "/management/ledger" }, { ...fin("Abroad Education revenue", "mgmt-006"), href: "/management/revenue/abroad" },
      { ...fin("IT Training revenue", "mgmt-007"), href: "/management/revenue/it" }, { ...fin("Recruitment revenue", "mgmt-008"), href: "/management/revenue/recruitment" },
      { ...fin("Expenses & rent", "mgmt-010"), href: "/management/expenses" }, { ...fin("Profit & loss", "mgmt-009"), href: "/management/pnl" }, { ...fin("Salaries", "mgmt-011"), href: "/management/salaries" },
      { ...fin("Accounts", "mgmt-013"), href: "/management/accounts" },
      { ...own("Investments & ROI", "mgmt-014"), href: "/management/investments" }, { ...own("Partner capital accounts", "mgmt-015"), href: "/management/capital" },
    ],
  },
  { title: "People", entries: [{ ...op("Trainers", "mgmt-017"), href: "/management/training#trainers" }, { ...op("Counselors", "mgmt-018"), href: "/management/counseling#counselors" }, { ...op("Telecallers", "mgmt-019"), href: "/management/telecalling#telecallers" }, { ...op("Recruiters", "mgmt-025"), href: "/management/recruitment#recruitment-kpis" }, { ...fin("Employee cost", "mgmt-011"), href: "/management/salaries#employee-cost" }] },
  { title: "Partnerships", entries: [{ ...op("Agents", "mgmt-021"), href: "/management/agents" }, op("Schools", "mgmt-022"), op("Universities", "mgmt-023"), { ...op("Companies", "mgmt-025"), href: "/management/recruitment#company-pipeline" }] },
  {
    title: "Business Intelligence",
    entries: [
      { ...op("Business snapshot", "mgmt-003"), href: "/management/snapshot" },
      own("This month's performance", "mgmt-031"), op("Next month plan & targets", "mgmt-026"), op("Long-term strategy", "mgmt-026"),
      { ...op("Discussions & decisions", "mgmt-027"), href: "/management/discussions" }, { ...op("To-do", "mgmt-028"), href: "/management/tasks" }, op("Meetings", "mgmt-029"), own("Business health score", "mgmt-030"),
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

/** The sidebar: the Command Center home, Management activity (every tier sees its own entries), then each live entry the tiers allow. */
export function managementNavFor(tiers: ManagementTiers, pillars: ManagementPillar[] = MANAGEMENT_PILLARS): NavItem[] {
  const live = pillarsFor(tiers, pillars).flatMap((pillar) => pillar.entries.flatMap((entry) => (entry.href ? [{ label: entry.label, href: entry.href }] : [])));
  // mgmt-028 (MT14): a caller outside the operational tier (the accountant) has no To-do, so their own Management tasks link instead.
  const myTasks = tiers.operational ? [] : [MANAGEMENT_TASKS_NAV];
  return [{ label: "Command Center", href: MANAGEMENT_HOME }, { label: "Management activity", href: MANAGEMENT_ACTIVITY }, ...live, ...myTasks];
}

// mgmt-002 (DEC-SCOPE-187 MA5-MA7): GET /management/activity. The API lists only the kinds the caller's tier may see and returns the
// kinds and actors it may filter by; the page passes the filters through as a GET form, so refresh, back and shared links keep them.
export const MANAGEMENT_ACTIVITY = "/management/activity";
export const ACTIVITY_PAGE_SIZE = 25;

export type ManagementActor = { id: string; full_name: string; role: string };
export type ManagementActivityItem = {
  id: string; at: string; actor: ManagementActor | null; kind: string; kind_label: string; verb: string; entity_id: string | null;
  fields: string[]; values: Record<string, { before: string | null; after: string | null }> | null; count: number | null;
};
export type ManagementActivityPage = {
  items: ManagementActivityItem[]; total: number; limit: number; offset: number;
  kinds: { value: string; label: string }[]; actors: ManagementActor[];
};
export type ActivityFilters = { actor: string; kind: string; date_from: string; date_to: string; offset: number };

const FILTER_KEYS = ["actor", "kind", "date_from", "date_to"] as const;
const VERB_LABEL: Record<string, string> = {
  create: "created", update: "changed", approve: "approved", complete: "completed", decide: "made", import: "imported",
  submit: "submitted", reject: "rejected", reverse: "reversed", download: "downloaded", // mgmt-004
};

const UUID_SHAPE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** The filters from the page's search params; anything else (or a repeated param) is dropped. A malformed actor id or an impossible
 * date only comes from a hand-edited address and is dropped too, so the API's only 422s are its own worded ones (kind, date order). */
export function activityFilters(search: Record<string, string | string[] | undefined>): ActivityFilters {
  const one = (key: string) => (typeof search[key] === "string" ? (search[key] as string) : "");
  const day = (key: string) => (isCalendarDate(one(key)) ? one(key) : "");
  const offset = Number.parseInt(one("offset"), 10);
  return { actor: UUID_SHAPE.test(one("actor")) ? one("actor") : "", kind: one("kind"), date_from: day("date_from"), date_to: day("date_to"), offset: offset > 0 ? offset : 0 };
}

function activityQuery(filters: ActivityFilters): URLSearchParams {
  const query = new URLSearchParams();
  for (const key of FILTER_KEYS) if (filters[key]) query.set(key, filters[key]);
  if (filters.offset > 0) query.set("offset", String(filters.offset));
  return query;
}

/** The page link for these filters (paging links reuse it with another offset). */
export function activityHref(filters: ActivityFilters): string {
  const query = activityQuery(filters).toString();
  return query ? `${MANAGEMENT_ACTIVITY}?${query}` : MANAGEMENT_ACTIVITY;
}

export function activityUrl(filters: ActivityFilters): string {
  const query = activityQuery(filters);
  query.set("limit", String(ACTIVITY_PAGE_SIZE));
  return `/api/v1${MANAGEMENT_ACTIVITY}?${query}`;
}

/** One entry in words: "Ledger entry approved", then the fields (with before → after where the API kept values) or a bulk count. */
export function describeActivity(item: ManagementActivityItem): { title: string; detail: string } {
  const title = `${item.kind_label} ${VERB_LABEL[item.verb] ?? item.verb}`;
  if (item.count !== null) return { title, detail: `${item.count} records` };
  const shown = (value: string | null) => value ?? "—";
  const detail = item.fields.map((field) => {
    const name = field.replaceAll("_", " ");
    const change = item.values?.[field];
    if (!change) return name;
    // Browser QA-01: a value set for the first time reads as the value, not "— → value".
    return change.before === null ? `${name}: ${shown(change.after)}` : `${name}: ${change.before} → ${shown(change.after)}`;
  });
  return { title, detail: detail.join(", ") };
}
