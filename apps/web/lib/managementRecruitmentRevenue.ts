// mgmt-008 (spec RR1-RR12): GET /management/revenue/recruitment -- Recruitment revenue by kind and the nine §6 KPIs for a month or its
// Indian financial year to date. The API decides access and every figure: the super admin's answer carries no money (RR9).
export const RECRUITMENT_REVENUE_HOME = "/management/revenue/recruitment";
export const RECRUITMENT_REVENUE_API = "/api/v1/management/revenue/recruitment";

export type Period = "month" | "year";
export type RecruitmentKpis = {
  recruiters: number; partner_companies: number; open_positions: number; candidates: number; interviews: number; selections: number;
  joining: number; placement_pct: number | null; revenue_per_placement: string | null;
}; // prettier-ignore
export type RecruitmentRevenue = {
  month: string; period: Period; start: string; end: string; label: string; kpi_end: string; revenue_visible: boolean;
  revenue: { total: string; kinds: { key: string; label: string; amount: string }[] } | null; kpis: RecruitmentKpis;
}; // prettier-ignore
export type RecruitmentRevenueQuery = { month: string; period: Period };

const MONTH = /^\d{4}-(0[1-9]|1[0-2])$/;

/** The page's address: a malformed or repeated value is dropped, so the API answers with its defaults. */
export function recruitmentRevenueQuery(search: Record<string, string | string[] | undefined>): RecruitmentRevenueQuery {
  const month = typeof search.month === "string" && MONTH.test(search.month) ? search.month : "";
  return { month, period: search.period === "year" ? "year" : "month" };
}

export function recruitmentRevenueUrl({ month, period }: RecruitmentRevenueQuery): string {
  return month || period === "year" ? `${RECRUITMENT_REVENUE_API}?${new URLSearchParams({ ...(month ? { month } : {}), period })}` : RECRUITMENT_REVENUE_API;
}
