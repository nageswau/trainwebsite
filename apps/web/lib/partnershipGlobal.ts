import type { PerformanceCommission } from "@/lib/commissionLedger";
import type { DashboardTile } from "@/lib/partnershipDashboard";
import type { PerformanceCounts, PerformanceStep, Period } from "@/lib/partnershipPerformance";
import { SEARCH_PATH } from "@/lib/universitySearch";

// upc-029 (spec GD1-GD17, EVID-020 §31): the complete global partnership dashboard for management. The API computes every figure over the
// reader's scope (head = team + unowned, super_admin = all); the columns and the pipeline are "now", the funnel and commission cover the
// period. `commission` is present only for the commission roles (U2).
export type GlobalCountry = { name: string; iso2: string | null; count: number };
export type GlobalUniversityRef = { id: string; university_code: string; name: string };
export type GlobalDashboard = Period & {
  today: string;
  active: {
    count: number; countries: GlobalCountry[]; universities: (GlobalUniversityRef & { country: string; courses: number })[];
    courses: { level: string; courses: number; universities: number }[];
  };
  in_progress: {
    count: number; expected: Record<"earlier" | "this_month" | "next_month" | "later" | "undated", number>;
    probability: { probability: number; count: number }[]; weighted: number;
    next_actions: { university: GlobalUniversityRef; task_id: string; title: string; due_on: string; overdue: boolean }[]; without_action: number;
  };
  target: {
    count: number; priorities: { priority: "A" | "B" | "C" | null; count: number }[]; countries: GlobalCountry[];
    course_levels: { level: string; count: number }[]; no_course_levels: number;
  };
  pipeline: { steps: { key: string; label: string; count: number }[]; lost: number; total: number };
  funnel: { steps: PerformanceStep[]; totals: PerformanceCounts };
  commission?: PerformanceCommission;
};

export const GLOBAL_URL = "/api/v1/partnership/global-dashboard";
export const GLOBAL_PATH = "/partnership/head/global-dashboard";
export const GLOBAL_READERS = new Set(["partnership_head", "super_admin"]);
export const EXPECTED_LABELS = { earlier: "Before this month", this_month: "This month", next_month: "Next month", later: "Later", undated: "Not dated" } as const;

const pipelineColumn = (column: string) => `/partnership/pipeline?column=${column}`;
// GD13: each Management §19 step opens the first §4 Kanban column it gathers.
const STEP_COLUMN: Record<string, string> = {
  identified: "target", contacted: "contacted", meeting: "meeting_scheduled", proposal: "proposal_sent", negotiation: "negotiation",
  agreement: "agreement_pending", signed: "signed", active_partner: "active_partners",
};

export const ACTIVE_HREF = pipelineColumn("active_partners");
export const PROGRESS_HREF = "/partnership/pipeline";
export const TARGET_HREF = pipelineColumn("target");

/** GD16: the upc-024 search for one partner status and one filter (it applies its own reader rule). */
export const searchHref = (status: "partner" | "in_progress" | "target", filter: Record<string, string>) =>
  `${SEARCH_PATH}?${new URLSearchParams({ partner_status: status, ...filter })}`;

export function pipelineTiles(d: GlobalDashboard): DashboardTile[] {
  return d.pipeline.steps.map((s) => ({ key: s.key, label: s.label, value: s.count, href: pipelineColumn(STEP_COLUMN[s.key]) }));
}
