import type { DiscussionPerson } from "@/lib/managementDiscussions";

// mgmt-026 (spec PN1-PN16): EVID-017 §25's next month plan and §26's target vs actual -- types, links and display. The API decides
// access (the operational tier), every item rule, the planning window, and each KPI's live actual (revenue only for partners, PN7).
export const PLANS_HOME = "/management/plans";
export const PLANS_API = "/api/v1/management/plans";

export type PlanStatus = "draft" | "active" | "closed";
export type KpiUnit = "count" | "inr";
export type PlanSummary = {
  id: string; month: string; status: PlanStatus; label: string; item_count: number; kpi_count: number; done_count: number; created_by: DiscussionPerson; updated_at: string;
};
export type PlanItem = { id: string; vertical: string; text: string; kpi: string | null; target: string | null; done: boolean; task_count: number; updated_at: string };
export type PlanDetail = PlanSummary & { items: PlanItem[] };
export type PlanPage = { items: PlanSummary[] };
export type PlanKpiOption = { key: string; label: string; unit: KpiUnit; definition: string };
export type PlanChoice = { key: string; label: string };
export type PlanOptions = { kpis: PlanKpiOption[]; verticals: PlanChoice[]; users: DiscussionPerson[]; current_month: string; max_month: string };
export type PlanProgressRow = { item_id: string; vertical: string; text: string; kpi: string; kpi_label: string; unit: KpiUnit; target: string; actual: string; achievement: number };
export type PlanProgress = {
  month: string; label: string; state: "upcoming" | "running" | "ended"; start: string; end: string; rows: PlanProgressRow[]; free_text: { total: number; done: number };
};

export const PLAN_STATUS_LABEL: Record<PlanStatus, string> = { draft: "Draft", active: "Active", closed: "Closed" };
export const PLAN_STATUS_CLASS: Record<PlanStatus, string> = { draft: "badge", active: "status", closed: "status closed" };

const MONTH_KEY = /^\d{4}-(0[1-9]|1[0-2])$/;
const MONTH = new Intl.DateTimeFormat("en-GB", { month: "long", year: "numeric", timeZone: "UTC" });
const COUNT = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const RUPEES = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });
const RUPEES_PAISE = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", minimumFractionDigits: 2 });

export const isMonthKey = (value: string) => MONTH_KEY.test(value);
export const planHref = (month: string) => `${PLANS_HOME}/${month}`;

/** "2026-10" -> "October 2026". */
export function monthLabel(month: string): string {
  return MONTH.format(new Date(`${month}-01T00:00:00Z`));
}

/** Every "YYYY-MM" from `first` to `last`, inclusive (the planning window the API returns). */
export function monthsBetween(first: string, last: string): string[] {
  const index = (key: string) => Number(key.slice(0, 4)) * 12 + Number(key.slice(5)) - 1;
  const months: string[] = [];
  for (let i = index(first); i <= index(last); i++) months.push(`${Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, "0")}`);
  return months;
}

/** A target or actual: a count as a whole number, revenue in rupees ("₹50,00,000"; paise only when there are any). */
export function formatTarget(value: string, unit: KpiUnit): string {
  const amount = Number(value);
  if (unit === "count") return COUNT.format(amount);
  return (Number.isInteger(amount) ? RUPEES : RUPEES_PAISE).format(amount);
}

export const formatAchievement = (achievement: number) => `${achievement}%`;

/** On target (100%+), close (75%+), or behind. */
export function achievementClass(achievement: number): string {
  return achievement >= 100 ? "status" : achievement >= 75 ? "status pending" : "status error";
}

/** Every vertical in the API's order with its items (an empty vertical stays, so an item can be added to it). */
export function groupByVertical<T extends { vertical: string }>(items: T[], verticals: PlanChoice[]): (PlanChoice & { items: T[] })[] {
  return verticals.map((v) => ({ ...v, items: items.filter((item) => item.vertical === v.key) }));
}
