import Link from "next/link";
import { notFound } from "next/navigation";

import { accessUnavailable } from "@/components/AccessUnavailable";
import { PerformanceFilters, PerformanceLoadError } from "@/components/BdmPerformanceControls";
import BdmPerformanceFigures from "@/components/BdmPerformanceFigures";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import {
  bdmPath, isBdmType, isPerformance, PERFORMANCE_PATH, performancePath, performanceUrl, periodText, readFilters, TYPE_LABEL, typePath, typeTotals,
} from "@/lib/bdmPerformance";
import { failureText, isDenied, load, managerOptions, shellFor } from "@/lib/bdmPerformancePage";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import type { User } from "@/lib/types";

type Search = { from?: string; to?: string; manager?: string };

// bdm-024 (DEC-SCOPE-111 P8, L2): the BDMs of one type with their figures for the period; the Total row is the type's column of the
// §5 table. Each BDM drills down to their organizations and trips. Inactive BDMs are listed (their records still count, P4).
export default async function BdmPerformanceTypePage({ params, searchParams }: { params: Promise<{ type: string }>; searchParams: Promise<Search> }) {
  const { type } = await params;
  if (!isBdmType(type)) notFound();
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  const { superAdmin, nav, roleLabel } = await shellFor(user);
  const filters = readFilters(await searchParams, superAdmin);
  const [data, managers] = await Promise.all([load(performanceUrl(filters, type), isPerformance), superAdmin ? managerOptions() : undefined]);
  if (data instanceof ApiError && isDenied(data)) return accessUnavailable(data, "/admin/login");
  const ok = !(data instanceof ApiError);
  const action = `${PERFORMANCE_PATH}/${type}`;
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <nav aria-label="Breadcrumb" className="muted" style={{ marginBottom: 8 }}>
          <Link href={performancePath(filters)} style={LINK_STYLE}>Performance</Link> › {TYPE_LABEL[type]}
        </nav>
        <div className="portal-title">
          <div>
            <div className="eyebrow">Performance</div>
            <h2>{`${TYPE_LABEL[type]}s`}</h2>
            {ok && <p className="muted">{`${data.manager ? `${data.manager.full_name}'s team · ` : ""}${periodText(data.from, data.to)}, India time (IST).`}</p>}
          </div>
        </div>
        <PerformanceFilters action={action} filters={filters} period={ok ? { from: data.from, to: data.to } : null} managers={managers} />
        {ok ? (
          <section className="card" aria-labelledby="performance-bdms">
            <h3 id="performance-bdms" style={{ margin: "0 0 8px", fontSize: 18 }}>BDMs</h3>
            <BdmPerformanceFigures
              caption={`${TYPE_LABEL[type]}s, ${periodText(data.from, data.to)}`} first="BDM" empty={`No ${TYPE_LABEL[type]}s in this team.`}
              total={typeTotals(data, type)}
              rows={data.bdms.map((b) => ({ key: b.id, name: b.full_name, href: bdmPath(b.id, filters), note: b.active ? undefined : "Inactive", figures: b.figures }))}
            />
          </section>
        ) : (
          <PerformanceLoadError message={failureText(data)} retryHref={typePath(type, filters)} resetHref={typePath(type, { manager: filters.manager })} />
        )}
      </div>
    </PortalShell>
  );
}
