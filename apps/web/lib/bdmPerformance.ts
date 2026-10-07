import { isUuid } from "@/lib/bdmTravel";
import { formatCalendarDate } from "@/lib/formatDate";

// bdm-024 (DEC-SCOPE-113): management performance by BDM type, its drill-down and the master view. The API computes and defines every
// figure; the web owns the links between levels (P8), which always carry the period and, for super_admin, the chosen manager.
const API = "/api/v1/bdm/manager";
export const PERFORMANCE_PATH = "/bdm/manager/performance";
export const HIERARCHY_PATH = "/bdm/manager/hierarchy";

export const BDM_TYPES = ["agent", "school", "college"] as const;
export type BdmType = (typeof BDM_TYPES)[number];
export const TYPE_LABEL: Record<BdmType, string> = { agent: "Agent BDM", school: "School BDM", college: "College BDM" };
export const isBdmType = (value: string | undefined): value is BdmType => BDM_TYPES.includes(value as BdmType);

/** A count, or for revenue an INR decimal string; null = not tracked. */
export type Value = number | string | null;
export type PerformanceCell = { type: BdmType; tracked: boolean; value: Value; definition: string };
export type PerformanceRow = { key: string; label: string; cells: PerformanceCell[] };
export type Figures = {
  meetings: number; trips: number | null; new_organizations: number; mous: number; leads: number; students: number; revenue: string | null;
};
export type PersonRef = { id: string; full_name: string };
export type PerformanceBdm = PersonRef & { active: boolean; figures: Figures };
export type Performance = { from: string; to: string; manager: PersonRef | null; type: BdmType | null; rows: PerformanceRow[]; bdms: PerformanceBdm[] };
export type PerformanceTrip = { id: string; code: string; from_place: string; to_place: string; travel_date: string; approval_status: string; travel_status: string };
export type BdmPerformance = {
  from: string; to: string; bdm: PersonRef & { active: boolean; bdm_type: BdmType }; totals: Figures;
  organizations: { id: string; code: string; name: string; figures: Figures }[]; trips: PerformanceTrip[];
};
export type ChainStep = { key: string; label: string; definition: string; tracked: boolean };
export type HierarchyOrganization = { id: string; code: string; name: string; counts: Value[] };
export type HierarchyBdm = PersonRef & { active: boolean; organization_count: number; not_linked: number; totals: Value[]; organizations: HierarchyOrganization[] };
export type HierarchyType = {
  type: BdmType; label: string; chain: ChainStep[]; bdm_count: number; organization_count: number; not_linked: number; totals: Value[]; bdms: HierarchyBdm[];
};
export type Hierarchy = { manager: PersonRef | null; as_of: string; types: HierarchyType[] };

/** The figure columns of the BDM and organization tables, in the §5 table's row order. */
export const FIGURE_COLUMNS: [keyof Figures, string][] = [
  ["meetings", "Meetings"], ["trips", "Travel Trips"], ["new_organizations", "New Organizations"], ["mous", "MoUs"], ["leads", "Leads"],
  ["students", "Students"], ["revenue", "Revenue"],
];

const ROW_FIGURE: Record<string, keyof Figures> = {
  "P-02": "meetings", "P-03": "trips", "P-04": "new_organizations", "P-05": "mous", "P-06": "leads", "P-07": "students", "P-08": "revenue",
};

/** One type's column of the §5 table as figures: the Total row of that type's BDM list (the level above, P8). */
export function typeTotals(data: Performance, type: BdmType): Figures {
  const out: Record<string, Value> = {};
  for (const row of data.rows) {
    const figure = ROW_FIGURE[row.key];
    if (figure) out[figure] = row.cells.find((c) => c.type === type)?.value ?? null;
  }
  return out as Figures;
}

/** The page's filters, as read from its URL: well-formed values only (anything else is dropped, and the API applies its default). */
export type Filters = { from?: string; to?: string; manager?: string };
const DAY = /^\d{4}-\d{2}-\d{2}$/;

export function readFilters(sp: { from?: string; to?: string; manager?: string }, superAdmin: boolean): Filters {
  return {
    from: sp.from && DAY.test(sp.from) ? sp.from : undefined,
    to: sp.to && DAY.test(sp.to) ? sp.to : undefined,
    manager: superAdmin && sp.manager && isUuid(sp.manager) ? sp.manager : undefined,
  };
}

function query(pairs: [string, string | undefined][]): string {
  const params = new URLSearchParams();
  for (const [key, value] of pairs) if (value) params.set(key, value);
  const text = params.toString();
  return text ? `?${text}` : "";
}

export const performanceUrl = (f: Filters, type?: BdmType): string =>
  `${API}/performance${query([["from", f.from], ["to", f.to], ["type", type], ["manager_user_id", f.manager]])}`;
export const bdmPerformanceUrl = (id: string, f: Filters): string => `${API}/performance/bdms/${encodeURIComponent(id)}${query([["from", f.from], ["to", f.to]])}`;
export const hierarchyUrl = (f: Filters): string => `${API}/hierarchy${query([["manager_user_id", f.manager]])}`;

const pageQuery = (f: Filters) => query([["from", f.from], ["to", f.to], ["manager", f.manager]]);
export const performancePath = (f: Filters): string => `${PERFORMANCE_PATH}${pageQuery(f)}`;
export const typePath = (type: BdmType, f: Filters): string => `${PERFORMANCE_PATH}/${type}${pageQuery(f)}`;
export const bdmPath = (id: string, f: Filters): string => `${PERFORMANCE_PATH}/bdms/${id}${pageQuery({ ...f, manager: undefined })}`;
export const organizationPath = (id: string): string => `/bdm/manager/organizations/${id}`;
export const tripPath = (id: string): string => `/bdm/manager/trips/${id}`;

/** "1,250" / "₹1,250.50" / "Not tracked" -- untracked is a label, never 0 (AC3). */
export function valueText(value: Value): string {
  if (value === null) return "Not tracked";
  if (typeof value === "string") return `₹${Number(value).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  return value.toLocaleString("en-IN");
}

/** "01 Oct 2026 – 31 Oct 2026" for the period's inclusive IST dates (calendar dates: no zone shift). */
export const periodText = (from: string, to: string): string => `${formatCalendarDate(from)} – ${formatCalendarDate(to)}`;

const isObject = (v: unknown): v is Record<string, unknown> => Boolean(v) && typeof v === "object";

export const isPerformance = (v: unknown): v is Performance =>
  isObject(v) && typeof v.from === "string" && typeof v.to === "string" && Array.isArray(v.rows) && Array.isArray(v.bdms);
export const isBdmPerformance = (v: unknown): v is BdmPerformance =>
  isObject(v) && isObject(v.bdm) && isObject(v.totals) && Array.isArray(v.organizations) && Array.isArray(v.trips);
export const isHierarchy = (v: unknown): v is Hierarchy => isObject(v) && typeof v.as_of === "string" && Array.isArray(v.types);
