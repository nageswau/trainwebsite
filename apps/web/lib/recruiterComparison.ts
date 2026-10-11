// rec-034 (DEC-SCOPE-183, API §12CX): Recruiter/BDM performance per recruiter -- the twelve §25 metrics (backlog Appendix B B1-B12),
// each credited by the API to the person who did the work. The period rules and errors are rec-033's (lib/recruiterPerformance).
import { performanceQuery } from "@/lib/recruiterPerformance";

export const COMPARISON_GROUPS = [
  {
    label: "Business development",
    figures: [
      { key: "companies_contacted", label: "Companies contacted" },
      { key: "meetings", label: "Meetings" },
      { key: "new_leads", label: "New recruiter leads" },
      { key: "new_companies", label: "New companies" },
      { key: "new_contracts", label: "New contracts" },
      { key: "new_requirements", label: "New requirements" },
    ],
  },
  {
    label: "Recruitment",
    figures: [
      { key: "candidates_sourced", label: "Candidates sourced" },
      { key: "profiles_shared", label: "Profiles shared" },
      { key: "interviews", label: "Interviews" },
      { key: "selections", label: "Selections" },
      { key: "joining", label: "Joining" },
      { key: "revenue", label: "Revenue" },
    ],
  },
] as const;
export type ComparisonKey = (typeof COMPARISON_GROUPS)[number]["figures"][number]["key"];
type CountKey = Exclude<ComparisonKey, "revenue">;

export type ComparisonRow = { user_id: string | null; full_name: string; active: boolean; revenue: string } & Record<CountKey, number>;
export type Comparison = {
  date_from: string; date_to: string; recruiter: { id: string; full_name: string } | null; items: ComparisonRow[]; totals: ComparisonRow | null;
};

export const COMPARISON_URL = "/api/v1/recruiter/performance/by-recruiter";
export const COMPARISON_PATH = "/recruiter/performance";

/** The same period, narrowed to one recruiter or widened back to the team. */
export const comparisonHref = (from: string, to: string, recruiter?: string) => COMPARISON_PATH + performanceQuery({ from, to, recruiter });
