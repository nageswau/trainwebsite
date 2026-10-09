import Link from "next/link";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PartnershipFunnel from "@/components/PartnershipFunnel";
import PerformancePeriodForm from "@/components/PerformancePeriodForm";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import {
  chosenPeriod,
  OPPORTUNITIES_PATH,
  PERFORMANCE_PATH,
  PERFORMANCE_READERS,
  PERFORMANCE_URL,
  type PerformancePage,
  periodLabel,
  periodQuery,
  type UniversityPerformance,
  universityPerformanceUrl,
} from "@/lib/partnershipPerformance";
import type { User } from "@/lib/types";
import { shellFor, universityPath } from "@/lib/universities";

type Search = { from?: string; to?: string; university_id?: string };

// upc-018 (§17, spec §5): the "Student Opportunities" menu -- the student funnel for a period, over every university in the reader's
// scope or, with `university_id` (from a university's page), for that one university (the source's "ABC University" example).
export default async function StudentOpportunitiesPage({ searchParams }: { searchParams: Promise<Search> }) {
  const search = await searchParams;
  const { period, note } = chosenPeriod(search.from, search.to);
  const universityId = search.university_id;
  let user: User;
  let all: PerformancePage | null = null;
  let one: UniversityPerformance | null = null;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (!PERFORMANCE_READERS.has(user.role)) return accessDenied(user, "University performance access required");
    if (universityId) one = await serverApi<UniversityPerformance>(universityPerformanceUrl(universityId, period));
    else all = await serverApi<PerformancePage>(`${PERFORMANCE_URL}?${periodQuery(period, { limit: "1", offset: "0" })}`);
  } catch (e) {
    return accessUnavailable(e, "/overseas/login");
  }
  const { nav, roleLabel } = shellFor(user.role);
  const data = (one ?? all)!;
  const name = one ? one.university.name : "all your universities";
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Student Opportunities</div>
            <h2>{one ? one.university.name : "Student opportunities"} — {periodLabel(period)}</h2>
            <p className="muted">
              {one
                ? `${one.university.country} · ${one.university.stage_label}. Students from shortlist to enrolment with this university.`
                : `Students from shortlist to enrolment across ${all!.total} ${all!.total === 1 ? "university" : "universities"} in your scope (partners, and any with activity in the period).`}
            </p>
            <PerformancePeriodForm action={OPPORTUNITIES_PATH} period={period} keep={universityId ? { university_id: universityId } : {}} />
            {note && <p className="muted">{note}</p>}
          </div>
        </div>
        <section className="action-card wide" aria-labelledby="funnel-heading">
          <h3 id="funnel-heading">Student funnel</h3>
          <PartnershipFunnel steps={data.steps} counts={one ? one.counts : all!.totals} label={`Student funnel: ${name}`} />
          <p className="kpi-note muted">
            Each step counts what happened in the period: shortlists, applications made, offers, deposits paid, visas approved and enrolments.
            Leads, Counselling and Profiles eligible are not tracked: those records have no university link.
          </p>
          <div className="actions" style={{ marginTop: 12 }}>
            {one && <Link className="btn ghost small" href={universityPath(one.university.id)}>Open university</Link>}
            {one && <Link className="btn ghost small" href={`${OPPORTUNITIES_PATH}?${periodQuery(period)}`}>All universities</Link>}
            <Link className="btn ghost small" href={`${PERFORMANCE_PATH}?${periodQuery(period)}`}>University performance</Link>
          </div>
        </section>
      </div>
    </PortalShell>
  );
}
