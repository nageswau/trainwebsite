import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import DiscussionsShell from "@/components/DiscussionsShell";
import ManagementPlanEditor from "@/components/ManagementPlanEditor";
import ManagementPlanProgress from "@/components/ManagementPlanProgress";
import { ApiError, serverApi } from "@/lib/api";
import { indiaToday } from "@/lib/bdmTravel";
import type { ManagementMe } from "@/lib/management";
import { isMonthKey, monthLabel, PLAN_STATUS_CLASS, PLAN_STATUS_LABEL, PLANS_API, PLANS_HOME, type PlanDetail, type PlanOptions, type PlanProgress } from "@/lib/managementPlans";

const UNAVAILABLE = "This plan is unavailable right now. Please try again.";
const PROGRESS_UNAVAILABLE = "Target vs actual is unavailable right now. Please try again.";

// mgmt-026 (EVID-017 §26 then §25, PN6/PN14): one month's target vs actual, then the plan by vertical. A malformed or unplanned month
// says so with a way back; the API refuses everyone outside the operational tier and the page then shows the access card.
export default async function ManagementPlanPage({ params }: { params: Promise<{ month: string }> }) {
  const { month } = await params;
  let me: ManagementMe;
  try {
    me = await serverApi<ManagementMe>("/api/v1/management/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  const back = <Link className="btn secondary" href={PLANS_HOME}>All plans</Link>;
  const missing = (message: string) => (
    <DiscussionsShell me={me} section="Next month plan" title="Plan not found" actions={back}>
      <p>{message}</p>
    </DiscussionsShell>
  );
  if (!isMonthKey(month)) return missing("That is not a month. Choose a plan from the list.");

  let plan: PlanDetail | null = null;
  let options: PlanOptions | null = null;
  let error = "";
  try {
    [plan, options] = await Promise.all([serverApi<PlanDetail>(`${PLANS_API}/${month}`), serverApi<PlanOptions>(`${PLANS_API}/options`)]);
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return accessUnavailable(e, "/admin/login");
    if (e instanceof ApiError && e.status === 404) return missing(`There is no plan for ${monthLabel(month)} yet. Plan it from the list.`);
    error = UNAVAILABLE;
  }
  let progress: PlanProgress | null = null;
  let progressError = "";
  if (plan) {
    try {
      progress = await serverApi<PlanProgress>(`${PLANS_API}/${month}/progress`);
    } catch {
      progressError = PROGRESS_UNAVAILABLE;
    }
  }
  return (
    <DiscussionsShell me={me} section="Next month plan" title={`Plan for ${monthLabel(month)}`} actions={back}
      intro={plan && <>Status: <span className={PLAN_STATUS_CLASS[plan.status]}>{PLAN_STATUS_LABEL[plan.status]}</span> · Created by {plan.created_by.full_name}</>}>
      {error && <p className="form-error" role="alert">{error}</p>}
      {plan && options && (
        <>
          <ManagementPlanProgress progress={progress} error={progressError} verticals={options.verticals} />
          <ManagementPlanEditor key={plan.id} plan={plan} options={options} today={indiaToday()} />
        </>
      )}
    </DiscussionsShell>
  );
}
