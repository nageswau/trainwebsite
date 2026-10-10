import Link from "next/link";
import type { ReactNode } from "react";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import GlobalCounts from "@/components/GlobalCounts";
import PartnershipDashboardTiles from "@/components/PartnershipDashboardTiles";
import PartnershipFunnel from "@/components/PartnershipFunnel";
import PerformancePeriodForm from "@/components/PerformancePeriodForm";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { amountsText } from "@/lib/commissionLedger";
import { weightedText } from "@/lib/partnershipExpected";
import {
  ACTIVE_HREF,
  EXPECTED_LABELS,
  GLOBAL_PATH,
  GLOBAL_READERS,
  GLOBAL_URL,
  type GlobalCountry,
  type GlobalDashboard,
  pipelineTiles,
  PROGRESS_HREF,
  searchHref,
  TARGET_HREF,
} from "@/lib/partnershipGlobal";
import { chosenPeriod, periodLabel, periodQuery } from "@/lib/partnershipPerformance";
import type { User } from "@/lib/types";
import { shellFor, universityPath } from "@/lib/universities";

type Search = { from?: string; to?: string };

const dayText = (day: string) => new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: "UTC" }).format(new Date(`${day}T00:00:00Z`));
const countryRows = (countries: GlobalCountry[], status: "partner" | "target") =>
  countries.map((c) => ({ key: c.iso2 ?? c.name, label: c.name, count: c.count, href: c.iso2 ? searchHref(status, { iso2: c.iso2 }) : undefined }));

function Column({ id, icon, title, count, href, children }: { id: string; icon: string; title: string; count: number; href: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className="panel global-column">
      <h3 id={id}>
        <span aria-hidden="true">{icon} </span>
        <Link href={href}>{title} ({count})</Link>
      </h3>
      {count === 0 ? <p className="muted">No universities in this column.</p> : children}
    </section>
  );
}

// upc-029 (EVID-020 §31, spec §4): the complete global partnership dashboard for management -- the three columns (Active Partners, In
// Progress, Target List) with their sub-views, the Management §19 pipeline, the student recruitment funnel and the university commission.
// The columns are "now"; the period (in the URL, a plain GET form) drives the funnel and the commission. The API is the gate and the scope.
export default async function GlobalDashboardPage({ searchParams }: { searchParams: Promise<Search> }) {
  const search = await searchParams;
  const { period, note } = chosenPeriod(search.from, search.to);
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (!GLOBAL_READERS.has(user.role)) return accessDenied(user, "The global partnership dashboard is for partnership heads and super admins");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  const { nav, roleLabel } = shellFor(user.role);
  const d = await serverApi<GlobalDashboard>(`${GLOBAL_URL}?${periodQuery(period)}`).catch(() => null);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Global Dashboard</div>
            <h2><span aria-hidden="true">🌍 </span>EduSphere Global Partnerships</h2>
            <p className="muted">
              {user.role === "partnership_head" ? "Your team's universities" : "Every university"}: where each partnership stands now, and student recruitment and
              commission for {periodLabel(period)}.
            </p>
            <PerformancePeriodForm action={GLOBAL_PATH} period={period} />
            {note && <p className="muted">{note}</p>}
          </div>
        </div>
        {d === null ? (
          <p className="muted" role="status">The global dashboard is unavailable right now. Please refresh in a moment.</p>
        ) : (
          <>
            <div className="global-columns">
              <Column id="global-active" icon="🟢" title="Active Partners" count={d.active.count} href={ACTIVE_HREF}>
                <GlobalCounts caption="Country-wise" rows={countryRows(d.active.countries, "partner")} />
                <h4>University-wise</h4>
                <ol className="global-list">
                  {d.active.universities.map((u) => (
                    <li key={u.id}>
                      <Link href={universityPath(u.id)}>{u.name}</Link> <span className="muted">· {u.country} · {u.courses} active {u.courses === 1 ? "course" : "courses"}</span>
                    </li>
                  ))}
                </ol>
                {d.active.count > d.active.universities.length && <p className="muted global-more">Showing {d.active.universities.length} of {d.active.count}, most courses first.</p>}
                <GlobalCounts
                  caption="Course-wise (active courses)"
                  rows={d.active.courses.map((c) => ({ key: c.level, label: c.level, count: c.courses, href: searchHref("partner", { level: c.level }) }))}
                />
              </Column>
              <Column id="global-progress" icon="🟡" title="In Progress" count={d.in_progress.count} href={PROGRESS_HREF}>
                <GlobalCounts
                  caption="Expected agreement date"
                  rows={Object.entries(EXPECTED_LABELS).map(([key, label]) => ({ key, label, count: d.in_progress.expected[key as keyof typeof EXPECTED_LABELS] }))}
                />
                <GlobalCounts caption="Probability" rows={d.in_progress.probability.map((p) => ({ key: String(p.probability), label: `${p.probability}%`, count: p.count }))} />
                <p className="muted global-more">Weighted forecast: {weightedText(d.in_progress.weighted)}</p>
                <h4>Next action</h4>
                <ol className="global-list">
                  {d.in_progress.next_actions.map((a) => (
                    <li key={a.task_id}>
                      <Link href={universityPath(a.university.id)}>{a.university.name}</Link> — {a.title}{" "}
                      <span className="muted no-wrap">· due {dayText(a.due_on)}</span>
                      {a.overdue && <> <span className="status error">Overdue</span></>}
                    </li>
                  ))}
                </ol>
                {d.in_progress.without_action > 0 && <p className="muted global-more">{d.in_progress.without_action} without an open task</p>}
              </Column>
              <Column id="global-target" icon="🔵" title="Target List" count={d.target.count} href={TARGET_HREF}>
                <GlobalCounts
                  caption="Priority"
                  rows={d.target.priorities.map((p) => ({
                    key: p.priority ?? "none", label: p.priority ? `Priority ${p.priority}` : "Not set", count: p.count,
                    href: p.priority ? searchHref("target", { priority: p.priority }) : undefined,
                  }))}
                />
                <GlobalCounts caption="Country" rows={countryRows(d.target.countries, "target")} />
                <GlobalCounts
                  caption="Course levels offered"
                  rows={[
                    ...d.target.course_levels.map((c) => ({ key: c.level, label: c.level, count: c.count })),
                    ...(d.target.no_course_levels > 0 ? [{ key: "none", label: "Not stated", count: d.target.no_course_levels }] : []),
                  ]}
                />
              </Column>
            </div>
            <PartnershipDashboardTiles id="global-pipeline" title="Partnership Pipeline" tiles={pipelineTiles(d)} />
            {d.pipeline.lost > 0 && <p className="muted global-more">Includes {d.pipeline.lost} lost / closed in the total of {d.pipeline.total}.</p>}
            <section aria-labelledby="global-funnel" className="kpi-group">
              <h3 id="global-funnel">Student Recruitment</h3>
              <PartnershipFunnel steps={d.funnel.steps} counts={d.funnel.totals} label={`Student recruitment, ${periodLabel(period)}`} />
            </section>
            {d.commission && (
              <section aria-labelledby="global-commission" className="kpi-group">
                <h3 id="global-commission">University Commission</h3>
                <dl className="kpi-grid dashboard-tiles">
                  <div className="kpi-tile"><dt>Expected (enrolled in the period)</dt><dd className="kpi-value">{amountsText(d.commission.expected)}</dd></div>
                  <div className="kpi-tile"><dt>Received (in the period)</dt><dd className="kpi-value">{amountsText(d.commission.received)}</dd></div>
                </dl>
              </section>
            )}
          </>
        )}
      </div>
    </PortalShell>
  );
}
