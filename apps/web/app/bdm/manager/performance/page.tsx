import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import { PerformanceFilters, PerformanceLoadError } from "@/components/BdmPerformanceControls";
import BdmPerformanceTable from "@/components/BdmPerformanceTable";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { HIERARCHY_PATH, isPerformance, PERFORMANCE_PATH, performancePath, performanceUrl, periodText, readFilters } from "@/lib/bdmPerformance";
import { failureText, isDenied, load, managerOptions, shellFor } from "@/lib/bdmPerformancePage";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import type { User } from "@/lib/types";

type Search = { from?: string; to?: string; manager?: string };

// bdm-024 (DEC-SCOPE-111): the §5 management view -- KPIs x BDM types for a period (default: this IST month), for a manager's team or,
// for super_admin, all teams or one manager's. Every number drills down to the BDMs of its type.
export default async function BdmPerformancePage({ searchParams }: { searchParams: Promise<Search> }) {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  const { superAdmin, nav, roleLabel } = await shellFor(user);
  const filters = readFilters(await searchParams, superAdmin);
  const [data, managers] = await Promise.all([load(performanceUrl(filters), isPerformance), superAdmin ? managerOptions() : undefined]);
  if (data instanceof ApiError && isDenied(data)) return accessUnavailable(data, "/admin/login");
  const ok = !(data instanceof ApiError);
  const team = ok && data.manager ? `${data.manager.full_name}'s team` : superAdmin ? "All BDM teams" : "Your team";
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Performance</div>
            <h2>{team}</h2>
            {ok && <p className="muted">{`${periodText(data.from, data.to)}, India time (IST).`}</p>}
          </div>
          <Link href={`${HIERARCHY_PATH}${filters.manager ? `?manager=${filters.manager}` : ""}`} style={LINK_STYLE}>Master view</Link>
        </div>
        <PerformanceFilters action={PERFORMANCE_PATH} filters={filters} period={ok ? { from: data.from, to: data.to } : null} managers={managers} />
        {ok ? (
          <BdmPerformanceTable data={data} filters={filters} />
        ) : (
          <PerformanceLoadError message={failureText(data)} retryHref={performancePath(filters)} resetHref={performancePath({ manager: filters.manager })} />
        )}
      </div>
    </PortalShell>
  );
}
