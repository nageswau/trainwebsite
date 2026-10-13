// mgmt-012 (spec MK1-MK14): the marketing budget & ROI page's types, links and the budget form's request body. The API decides access
// (lead figures for every management role, money for the finance tier only) and every rule; this module only shapes what the page
// sends and shows.
import { rupees } from "@/lib/investments";

export const MARKETING_HOME = "/management/marketing";
export const MARKETING_API = "/api/v1/management/marketing";

export type MarketingFigures = {
  budget: string | null; spend: string | null; leads: number; qualified: number; customers: number; conversion: number | null;
  revenue: string | null; roi: number | null;
};
export type MarketingChannel = MarketingFigures & { channel: string; label: string };
export type MarketingCampaign = { id: string; name: string; channel: string; label: string; active: boolean; leads: number; qualified: number; customers: number };
export type MarketingGroups = { social: number; website: number; school: number; college: number; agent: number; influencer: number | null; events: number };
export type MarketingMonth = {
  month: string; current_month: string; money_visible: boolean; channels: MarketingChannel[]; totals: MarketingFigures; groups: MarketingGroups;
  campaigns: MarketingCampaign[]; budgets_updated_at: string | null; budgets_updated_by: { id: string; full_name: string } | null;
};
export type BudgetDraft = Record<string, string>;

export const marketingUrl = (month: string) => (month ? `${MARKETING_API}?month=${month}` : MARKETING_API);
export const budgetsUrl = (month: string) => `${MARKETING_API}/budgets?month=${month}`;

/** ROI or conversion as "488.2%"; a dash when there is none (no spend, or no leads). */
export const percentText = (value: number | null) => (value === null ? "—" : `${value.toLocaleString("en-IN", { maximumFractionDigits: 1 })}%`);

/** MK3: no budget row reads "Not set"; ₹0 is a budget of nothing. */
export const budgetText = (budget: string | null) => (budget === null ? "Not set" : rupees(budget));

/** MK4: the whole month, in channel order. A blank field is left out (no budget); anything typed is sent as written, so the API's 422
 * names it. */
export function budgetsBody(draft: BudgetDraft, channels: string[]): { budgets: { channel: string; amount: string }[] } {
  return { budgets: channels.flatMap((channel) => (draft[channel]?.trim() ? [{ channel, amount: draft[channel].trim() }] : [])) };
}

/** The API's 422 items (`loc: ["body", "budgets", i, field]`) placed on the channel sent at index i. */
export function budgetErrors(detail: unknown, sent: string[]): Record<string, string> {
  if (!Array.isArray(detail)) return {};
  const out: Record<string, string> = {};
  for (const item of detail as { loc?: unknown[]; msg?: string }[]) {
    const [where, list, index] = item.loc ?? [];
    if (where === "body" && list === "budgets" && typeof index === "number" && sent[index]) out[sent[index]] = String(item.msg);
  }
  return out;
}
