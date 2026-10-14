import { accessUnavailable } from "@/components/AccessUnavailable";
import DiscussionsShell from "@/components/DiscussionsShell";
import ManagementPlanForm from "@/components/ManagementPlanForm";
import ManagementPlans from "@/components/ManagementPlans";
import { ApiError, serverApi } from "@/lib/api";
import type { ManagementMe } from "@/lib/management";
import { PLANS_API, type PlanOptions, type PlanPage } from "@/lib/managementPlans";

const UNAVAILABLE = "Plans are unavailable right now. Please try again.";

// mgmt-026 (EVID-017 §25, PN2/PN14): every month's plan and "Plan a month". The API refuses everyone outside the operational tier (the
// accountant included, M13), and the page then shows the access card.
export default async function ManagementPlansPage() {
  let me: ManagementMe;
  try {
    me = await serverApi<ManagementMe>("/api/v1/management/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  let data: PlanPage | null = null;
  let options: PlanOptions | null = null;
  let error = "";
  try {
    [data, options] = await Promise.all([serverApi<PlanPage>(PLANS_API), serverApi<PlanOptions>(`${PLANS_API}/options`)]);
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return accessUnavailable(e, "/admin/login");
    error = UNAVAILABLE;
  }
  return (
    <DiscussionsShell me={me} section="Next month plan" title="Next month plan & targets"
      intro="Plan each month by vertical. Items with a KPI get a live actual against their target; other items are ticked done.">
      {data && options && <ManagementPlanForm first={options.current_month} last={options.max_month} planned={data.items.map((p) => p.month)} />}
      <ManagementPlans data={data} error={error} />
    </DiscussionsShell>
  );
}
