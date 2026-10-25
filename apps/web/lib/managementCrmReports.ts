import { isCalendarDate } from "@/lib/formatDate";

// ccrm-034 (DEC-SCOPE-267, R1-R10): GET /management/crm-reports -- six reports (ageing, university performance, visa outcomes, document
// readiness, lead conversion by intake, forecast by intake), each with its rows, a total row and its definitions. The API decides access
// (partner, super_admin, overseas_admin) and every count; the pages hold the filters in the address (a GET form), as mgmt-024 does.
export const CRM_REPORTS_HOME = "/management/crm-reports";
export const ADMIN_CRM_REPORTS_HOME = "/overseas/admin/crm-reports";
export const CRM_REPORTS_API = "/api/v1/management/crm-reports";
export const CRM_REPORTS_UNAVAILABLE = "The CRM reports are unavailable right now. Please try again.";

export const CRM_FILTER_KEYS = ["date_from", "date_to", "counselor", "country", "university", "course", "intake"] as const;
export type CrmFilterKey = (typeof CRM_FILTER_KEYS)[number];
export type CrmFilters = Record<CrmFilterKey, string>;
export const EMPTY_CRM_FILTERS: CrmFilters = Object.fromEntries(CRM_FILTER_KEYS.map((key) => [key, ""])) as CrmFilters;

export type CrmChoice = { value: string; label: string };
export type CrmDefinition = { key: string; label: string; definition: string };
type Counts = { applications: number; students: number };
export type AgeingBands = { d0_7: number; d8_14: number; d15_30: number; d31_60: number; d61_plus: number };
export type AgeingTotal = Counts & { bands: AgeingBands; oldest_days: number | null };
export type AgeingRow = AgeingTotal & { stage: string; stage_label: string; sub_status: string | null; sub_status_label: string };
export type UniversityTotal = Counts & { offers: number; offer_rate: number | null; rejections: number; acceptances: number; enrollments: number };
export type UniversityRow = UniversityTotal & { university_id: string; label: string };
export type VisaTotal = Counts & { submitted: number; pending: number; approved: number; refused: number; enrolled: number };
export type VisaRow = VisaTotal & { country_id: string; label: string };
export type ReadinessTotal = Counts & { ready: number; blocked: number; needs_override: number; no_checklist: number };
export type ReadinessRow = ReadinessTotal & { stage: string; stage_label: string };
export type LeadTotal = { leads: number; converted: number; conversion_pct: number | null; students: number; applications: number };
export type LeadRow = LeadTotal & { intake: string | null; label: string };
export type ForecastTotal = Counts & { confirmed: number; expected: number; possible: number; lost: number; forecast: number };
export type ForecastRow = ForecastTotal & { intake: string | null; label: string };
export type CrmReport<Row, Total> = { definitions: CrmDefinition[]; rows: Row[]; total: Total };
export type CrmReports = {
  filters: Record<CrmFilterKey, string | null>;
  as_of: string;
  ageing: CrmReport<AgeingRow, AgeingTotal>;
  universities: CrmReport<UniversityRow, UniversityTotal>;
  visa: CrmReport<VisaRow, VisaTotal>;
  readiness: CrmReport<ReadinessRow, ReadinessTotal>;
  leads: CrmReport<LeadRow, LeadTotal>;
  forecast: CrmReport<ForecastRow, ForecastTotal>;
  options: Record<"counselors" | "countries" | "universities" | "courses" | "intakes", CrmChoice[]>;
};

const UUID_SHAPE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function valid(key: CrmFilterKey, value: string): boolean {
  if (key === "date_from" || key === "date_to") return isCalendarDate(value);
  if (key === "intake") return value.trim() !== "" && value.length <= 80; // the API's limit
  return UUID_SHAPE.test(value) || (key === "counselor" && value === "none");
}

/** The filters from the page's search params; a repeated, malformed or unknown value only comes from a hand-edited address and is dropped. */
export function crmFilters(search: Record<string, string | string[] | undefined>): CrmFilters {
  const filters = { ...EMPTY_CRM_FILTERS };
  for (const key of CRM_FILTER_KEYS) {
    const value = search[key];
    if (typeof value === "string" && valid(key, value)) filters[key] = value;
  }
  return filters;
}

export function hasCrmFilters(filters: CrmFilters): boolean {
  return CRM_FILTER_KEYS.some((key) => filters[key] !== "");
}

function withQuery(path: string, filters: CrmFilters): string {
  const query = new URLSearchParams();
  for (const key of CRM_FILTER_KEYS) if (filters[key]) query.set(key, filters[key]);
  const text = query.toString();
  return text ? `${path}?${text}` : path;
}

export const crmReportsUrl = (filters: CrmFilters) => withQuery(CRM_REPORTS_API, filters);
/** The page's own address for these filters -- only the set ones, so a link is short and shareable. */
export const crmReportsHref = (home: string, filters: CrmFilters) => withQuery(home, filters);

export function percentText(value: number | null): string {
  return value === null ? "—" : `${value}%`;
}
