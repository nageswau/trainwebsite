import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import BdmHierarchy from "@/components/BdmHierarchy";
import { PerformanceFilters, PerformanceLoadError } from "@/components/BdmPerformanceControls";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { HIERARCHY_PATH, hierarchyUrl, isHierarchy, performancePath, readFilters } from "@/lib/bdmPerformance";
import { failureText, isDenied, load, managerOptions, shellFor } from "@/lib/bdmPerformancePage";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import type { User } from "@/lib/types";

// bdm-024 (DEC-SCOPE-111 P10/P11): the §6 BDM master view -- each BDM type, its BDMs and their linked organizations with the type's
// value chain. Live, all-time figures (the organization panels' own).
export default async function BdmHierarchyPage({ searchParams }: { searchParams: Promise<{ manager?: string }> }) {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  const { superAdmin, nav, roleLabel } = await shellFor(user);
  const filters = readFilters(await searchParams, superAdmin);
  const [data, managers] = await Promise.all([load(hierarchyUrl(filters), isHierarchy), superAdmin ? managerOptions() : undefined]);
  if (data instanceof ApiError && isDenied(data)) return accessUnavailable(data, "/admin/login");
  const ok = !(data instanceof ApiError);
  const here = `${HIERARCHY_PATH}${filters.manager ? `?manager=${filters.manager}` : ""}`;
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Master view</div>
            <h2>{ok && data.manager ? `${data.manager.full_name}'s team` : superAdmin ? "All BDM teams" : "Your team"}</h2>
            <p className="muted">Live figures, all time. Open a BDM to see their linked organizations.</p>
          </div>
          <Link href={performancePath({ manager: filters.manager })} style={LINK_STYLE}>Performance by period</Link>
        </div>
        {managers && <PerformanceFilters action={HIERARCHY_PATH} filters={filters} period={null} managers={managers} />}
        {ok ? <BdmHierarchy data={data} /> : <PerformanceLoadError message={failureText(data)} retryHref={here} resetHref={here} />}
      </div>
    </PortalShell>
  );
}
