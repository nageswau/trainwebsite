// hrc-034 (DEC-SCOPE-415): skill demand, portal analytics and data quality. The API decides who reads them (`reports.recruitment_insights.view`) and
// computes every figure; this file only names the pages and builds addresses. A page's state lives in its address, so refresh, back and links keep it.
const API = "/api/v1/recruiter/recruitment-insights";
export const INSIGHTS_BASE = "/recruiter/insights";
export const INSIGHTS_PAGES = [
  { key: "skill-demand", label: "Skill demand" },
  { key: "portal-analytics", label: "Portal analytics" },
  { key: "data-quality", label: "Data quality" },
] as const;
export type InsightsPageKey = (typeof INSIGHTS_PAGES)[number]["key"];
export const PAGE_SIZE = 50;
export const DEFAULT_N = 5;

export type Figure = { key: string; label: string; value: number; definition: string; href?: string | null };
export type SkillRow = { skill_id: string; name: string; category: string; required_jobs: number; preferred_jobs: number; open_jobs: number; supply: number; zero_supply: boolean };
export type SkillSort = "demand" | "supply";
export type SkillDemand = { figures: Figure[]; items: SkillRow[]; total: number; limit: number; offset: number; sort: SkillSort };
export type VacancyRow = { id: string; code: string; title: string; company: string; matches: number; reason: string | null };
export type Vacancies = { n: number; items: VacancyRow[]; total: number; limit: number; offset: number; checked: number; open_jobs: number };
export type FunnelStep = { key: string; label: string; events: number; people: number; dropped: number | null };
export type PortalAnalytics = {
  from: string; to: string; registrations: { total: number; verified: number }; completion: { label: string; count: number }[];
  funnel: FunnelStep[]; first_recorded: string | null;
};
export type DataQuality = { figures: Figure[] };
export type DrillValue = string | number | string[] | null;
export type Drill = {
  figure: { key: string; label: string; definition: string }; columns: { key: string; label: string }[];
  items: Record<string, DrillValue>[]; total: number; limit: number; offset: number;
};
type Params = Record<string, string | string[] | undefined>;

const text = (value: unknown): string => (typeof value === "string" ? value : "");
const whole = (value: unknown, fallback: number, min = 0, max = Number.MAX_SAFE_INTEGER): number => {
  const raw = text(value);
  if (!/^\d+$/.test(raw)) return fallback;
  const n = Number(raw);
  return n >= min && n <= max ? n : fallback;
};

export const parseSkill = (p: Params) => ({
  sort: (text(p.sort) === "supply" ? "supply" : "demand") as SkillSort, offset: whole(p.offset, 0), n: whole(p.n, DEFAULT_N, 1, 100), vacancyOffset: whole(p.vacancy_offset, 0),
});
export type SkillParams = ReturnType<typeof parseSkill>;
export const parsePeriod = (p: Params) => ({ from: /^\d{4}-\d{2}-\d{2}$/.test(text(p.from)) ? text(p.from) : "", to: /^\d{4}-\d{2}-\d{2}$/.test(text(p.to)) ? text(p.to) : "" });
export const parseDrill = (p: Params) => ({ figure: text(p.figure), offset: whole(p.offset, 0) });

function address(path: string, values: Record<string, string | number>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) if (value !== "" && value !== 0) query.set(key, String(value));
  const tail = query.toString();
  return tail ? `${path}?${tail}` : path;
}

export const skillDemandUrl = ({ sort, offset }: SkillParams) => address(`${API}/skill-demand`, { sort, offset, limit: PAGE_SIZE });
export const vacanciesUrl = ({ n, vacancyOffset }: SkillParams) => address(`${API}/skill-demand/vacancies`, { n, offset: vacancyOffset, limit: PAGE_SIZE });
export const portalAnalyticsUrl = (period: { from: string; to: string }) => address(`${API}/portal-analytics`, period);
export const dataQualityUrl = `${API}/data-quality`;
export const drillUrl = (figure: string, offset: number) => address(`${API}/data-quality/${encodeURIComponent(figure)}`, { offset, limit: PAGE_SIZE });

export const skillHref = (s: SkillParams, change: Partial<SkillParams> = {}) => {
  const { sort, offset, n, vacancyOffset } = { ...s, ...change };
  return address(`${INSIGHTS_BASE}/skill-demand`, { ...(sort === "supply" ? { sort } : {}), offset, ...(n === DEFAULT_N ? {} : { n }), vacancy_offset: vacancyOffset });
};
export const drillHref = (figure: string, offset = 0) => address(`${INSIGHTS_BASE}/data-quality`, { figure, offset });
