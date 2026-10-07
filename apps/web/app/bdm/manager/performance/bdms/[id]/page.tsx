import Link from "next/link";
import { notFound } from "next/navigation";

import { accessUnavailable } from "@/components/AccessUnavailable";
import { PerformanceFilters, PerformanceLoadError, resetTo } from "@/components/BdmPerformanceControls";
import BdmPerformanceFigures from "@/components/BdmPerformanceFigures";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import {
  bdmPath, bdmPerformanceUrl, isBdmPerformance, organizationPath, PERFORMANCE_PATH, performancePath, periodText, readFilters, TYPE_LABEL, tripPath,
  typePath,
} from "@/lib/bdmPerformance";
import { failureText, isDenied, load, shellFor } from "@/lib/bdmPerformancePage";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { APPROVAL_LABEL, isUuid, TRAVEL_LABEL } from "@/lib/bdmTravel";
import { tripDateText } from "@/lib/bdmMyDay";
import type { User } from "@/lib/types";

type Search = { from?: string; to?: string };

// bdm-024 (DEC-SCOPE-111 P8/P9, L3): one BDM's organizations with a figure in the period (each links to its page: appointments,
// outcomes, leads and the student / revenue panels), and their trips (trips belong to the BDM, not to an organization).
export default async function BdmPerformanceBdmPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<Search> }) {
  const { id } = await params;
  if (!isUuid(id)) notFound();
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  const { nav, roleLabel } = await shellFor(user);
  const filters = readFilters(await searchParams, false);
  const data = await load(bdmPerformanceUrl(id, filters), isBdmPerformance);
  if (data instanceof ApiError && isDenied(data)) return accessUnavailable(data, "/admin/login");
  const ok = !(data instanceof ApiError);
  const action = `${PERFORMANCE_PATH}/bdms/${id}`;
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <nav aria-label="Breadcrumb" className="muted" style={{ marginBottom: 8 }}>
          <Link href={performancePath(filters)} style={LINK_STYLE}>Performance</Link>
          {ok && <> › <Link href={typePath(data.bdm.bdm_type, filters)} style={LINK_STYLE}>{TYPE_LABEL[data.bdm.bdm_type]}</Link> › {data.bdm.full_name}</>}
        </nav>
        <div className="portal-title">
          <div>
            <div className="eyebrow">Performance</div>
            <h2>{ok ? data.bdm.full_name : "BDM performance"} {ok && !data.bdm.active && <span className="badge">Inactive</span>}</h2>
            {ok && <p className="muted">{`${TYPE_LABEL[data.bdm.bdm_type]} · ${periodText(data.from, data.to)}, India time (IST).`}</p>}
          </div>
        </div>
        <PerformanceFilters action={action} filters={filters} period={ok ? { from: data.from, to: data.to } : null} />
        {ok ? (
          <>
            <section className="card" aria-labelledby="performance-organizations" style={{ marginBottom: 16 }}>
              <h3 id="performance-organizations" style={{ margin: 0, fontSize: 18 }}>Organizations</h3>
              <p className="muted" style={{ margin: "4px 0 8px" }}>
                These figures count the period only. Each organization&apos;s page lists all its appointments, outcomes and leads, and its
                student and revenue panels show all-time figures.
              </p>
              <BdmPerformanceFigures
                caption={`${data.bdm.full_name}'s organizations, ${periodText(data.from, data.to)}`} first="Organization" total={data.totals}
                empty="No organization has a figure in this period."
                rows={data.organizations.map((o) => ({ key: o.id, name: o.name, href: organizationPath(o.id), note: o.code, figures: o.figures }))}
              />
            </section>
            <section className="card" aria-labelledby="performance-trips">
              <h3 id="performance-trips" style={{ margin: 0, fontSize: 18 }}>{`Travel trips: ${data.trips.length}`}</h3>
              {data.trips.length === 0 ? (
                <p className="muted">No trips in this period.</p>
              ) : (
                <ul style={{ listStyle: "none", padding: 0, margin: "8px 0 0" }}>
                  {data.trips.map((t) => (
                    <li key={t.id} style={{ padding: "8px 0", borderTop: "1px solid var(--line, #e5e7eb)", overflowWrap: "anywhere" }}>
                      <Link href={tripPath(t.id)} style={LINK_STYLE}>{`${t.code} · ${t.from_place} → ${t.to_place}`}</Link>
                      <span className="muted">
                        {` · ${tripDateText(t.travel_date)} · ${APPROVAL_LABEL[t.approval_status as keyof typeof APPROVAL_LABEL] ?? t.approval_status}, `}
                        {`${TRAVEL_LABEL[t.travel_status as keyof typeof TRAVEL_LABEL] ?? t.travel_status}`}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </>
        ) : (
          <PerformanceLoadError message={failureText(data)} retryHref={bdmPath(id, filters)} reset={resetTo(action, undefined)} />
        )}
      </div>
    </PortalShell>
  );
}
