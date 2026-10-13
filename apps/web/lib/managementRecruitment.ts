import { telecallingFilters, type TelecallingFilters } from "@/lib/managementTelecalling";

// mgmt-025 (EVID-017 §21, spec RC1-RC12): GET /management/recruitment -- the eleven Recruiter KPIs over a period (default this month to
// date) and the company pipeline now. The API decides access (operational tier), the period rules and every count; revenue comes only
// for the finance tier (`revenue_visible`). The page holds the dates in the address, as the Telecalling dashboard does.
export const RECRUITMENT_HOME = "/management/recruitment";
const RECRUITMENT_API = "/api/v1/management/recruitment";

export type RecruitmentKpis = {
  recruiters: number; employer_partners: number; new_companies: number; job_openings: number; internship_openings: number; candidates: number;
  interviews: number; selections: number; joining: number; placement_rate: number | null; revenue: string | null;
}; // prettier-ignore
export type RecruitmentStep = { key: string; label: string; value: number };
export type Recruitment = {
  date_from: string; date_to: string; revenue_visible: boolean; kpis: RecruitmentKpis; pipeline: RecruitmentStep[]; requirement_closed: number;
  lost: number;
}; // prettier-ignore

// The source's eleven KPIs (§21), in its order and words.
export const RECRUITMENT_KPIS: { key: keyof RecruitmentKpis; label: string }[] = [
  { key: "recruiters", label: "Recruiters" }, { key: "employer_partners", label: "Employer partners" },
  { key: "new_companies", label: "New companies" }, { key: "job_openings", label: "Job openings" },
  { key: "internship_openings", label: "Internship openings" }, { key: "candidates", label: "Candidates" },
  { key: "interviews", label: "Interviews" }, { key: "selections", label: "Selections" }, { key: "joining", label: "Joining" },
  { key: "placement_rate", label: "Placement rate" }, { key: "revenue", label: "Revenue" },
]; // prettier-ignore

export type RecruitmentFilters = TelecallingFilters;

/** The dates from the page's search params (the Telecalling dashboard's rule: a repeated or impossible date is dropped). */
export const recruitmentFilters = telecallingFilters;

function withQuery(path: string, filters: RecruitmentFilters): string {
  const query = new URLSearchParams(Object.entries(filters).filter(([, value]) => value)).toString();
  return query ? `${path}?${query}` : path;
}

export const recruitmentUrl = (filters: RecruitmentFilters) => withQuery(RECRUITMENT_API, filters);
export const recruitmentHref = (filters: RecruitmentFilters) => withQuery(RECRUITMENT_HOME, filters);

/** RC7: "12.5%", or a dash when nobody was sourced in the period. */
export const placementRateText = (rate: number | null) => (rate === null ? "—" : `${rate}%`);
