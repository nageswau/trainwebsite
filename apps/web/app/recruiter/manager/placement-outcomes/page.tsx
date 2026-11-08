import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PlacementOutcomesPanel from "@/components/PlacementOutcomesPanel";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { OUTCOMES_URL, outcomeParams, outcomeQuery, outcomesError, type Outcomes } from "@/lib/placementOutcomes";
import { companyShell } from "@/lib/recruiterCompanies";
import { istToday } from "@/lib/telecallerTargets";
import type { User } from "@/lib/types";

const ROLES = ["placement_manager", "super_admin"]; // R1

// pob-029 (DEC-SCOPE-438): placement outcome reports for the Team Lead and super_admin. The role check only spares other roles a screen
// that can only fail; the API decides the scope (a Team Lead's team + Unassigned) and whether the revenue figures are shown.
export default async function PlacementOutcomesPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const params = outcomeParams(await searchParams);
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  if (!ROLES.includes(user.role)) return accessDenied(user, "Team Lead or administrator role required");
  let data: Outcomes | null = null;
  let error = "";
  try {
    data = await serverApi<Outcomes>(OUTCOMES_URL + outcomeQuery(params));
  } catch (e) {
    if (e instanceof ApiError && e.status === 403) return accessUnavailable(e, "/admin/login");
    error = outcomesError(e);
  }
  const { nav, roleLabel } = companyShell(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Reports</div>
            <h2>Placement outcomes</h2>
            <p className="muted">
              {user.role === "placement_manager" ? "Your team's" : "All"} placements whose offer was accepted in the period, by company, vendor, role,
              source, recruiter or placement officer, with conversions, joining, revenue, replacements and satisfaction. Rates show &ldquo;—&rdquo; when there is nothing to divide by.
            </p>
          </div>
        </div>
        <PlacementOutcomesPanel data={data} error={error} params={params} today={istToday()} />
      </div>
    </PortalShell>
  );
}
