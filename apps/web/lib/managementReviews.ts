import { formatInr } from "@/lib/managementLedger";
import type { KpiUnit } from "@/lib/managementPlans";

// mgmt-032 (EVID-017 §32, DEC-SCOPE-220 MR1-MR14): the Monthly Business Review, partners only. The API stores each review's figures as
// a frozen snapshot (money as exact decimal strings), so the page and the PDF render the same document.
export const REVIEWS_HOME = "/management/reviews";
export const REVIEWS_API = "/api/v1/management/reviews";
export const reviewHref = (month: string) => `${REVIEWS_HOME}/${month}`;
export const reviewApi = (month: string) => `${REVIEWS_API}/${month}`;

export type ReviewStatus = "draft" | "final";
export const REVIEW_STATUS_LABEL: Record<ReviewStatus, string> = { draft: "Draft", final: "Final" };
export const REVIEW_STATUS_CLASS: Record<ReviewStatus, string> = { draft: "badge", final: "status" };

export const PROBLEM_PROMPTS = [["went_wrong", "What went wrong?"], ["delayed", "What is delayed?"], ["intervention", "What needs management intervention?"]] as const;
export const NEXT_MONTH_PROMPTS = [["initiatives", "New initiatives"], ["hiring", "Hiring"], ["investments", "Investments"], ["partnerships", "Partnerships"]] as const;
export type NarrativeKey = (typeof PROBLEM_PROMPTS)[number][0] | (typeof NEXT_MONTH_PROMPTS)[number][0];
export type ReviewNarrative = Record<NarrativeKey, string>;

type Line = { key: string; label: string; amount: string };
type Money = string | null;
export type ReviewSnapshot = {
  revenue: { lines: Line[]; total: string };
  expenses: { lines: Line[]; total: string };
  profitability: { revenue: string; expenses: string; net_profit: string; margin: number | null };
  sales: { leads: number; students: number; applications: number; enrollments: number; placements: number };
  partnerships: { agents: number; schools: number; universities: number; companies: number };
  people: { employees: number | null; departments: { name: string; headcount: number; total_cost: string }[]; attendance: null; attendance_note: string; productivity: Money };
  marketing: { budget: Money; spend: Money; leads: number; customers: number; conversion: number | null; revenue: Money; roi: number | null };
  investments: { new_count: number; new_amount: string; total: string; return: string; roi: Money };
  next_month: { month: string; label: string; targets: { vertical: string; text: string; kpi: string; unit: KpiUnit; target: string }[]; budget: Money };
};
type Person = { id: string; full_name: string };
export type MonthlyReview = {
  id: string; month: string; label: string; status: ReviewStatus; snapshot: ReviewSnapshot; narrative: ReviewNarrative;
  generated_at: string; finalised_at: string | null; finalised_by: Person | null; updated_at: string; updated_by: Person | null;
};
export type ReviewSummary = { month: string; label: string; status: ReviewStatus; generated_at: string; finalised_at: string | null };
export type ReviewPage = { items: ReviewSummary[] };

export const NONE = "—";
export const inrOrNone = (amount: Money) => (amount === null ? NONE : formatInr(amount));
const PERCENT = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });
export const formatPercent = (value: number | string | null) => (value === null ? NONE : `${PERCENT.format(Number(value))}%`);

/** The `count` months before `today`'s (an IST "YYYY-MM-DD"), newest first, without those already reviewed: what can be generated. */
export function finishedMonths(today: string, reviewed: string[], count = 24): string[] {
  const start = Number(today.slice(0, 4)) * 12 + Number(today.slice(5, 7)) - 1;
  const months: string[] = [];
  for (let i = start - 1; i >= start - count; i--) months.push(`${Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, "0")}`);
  return months.filter((m) => !reviewed.includes(m));
}

/** The Problems questions still unanswered (finalising needs all three, MR13); the message is the API's own 422 wording. */
export function missingProblems(narrative: ReviewNarrative): string {
  const missing = PROBLEM_PROMPTS.filter(([key]) => !narrative[key].trim()).map(([, label]) => label);
  return missing.length ? `Answer every Problems question before finalising: ${missing.join(", ")}` : "";
}
