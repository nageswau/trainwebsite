import Link from "next/link";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import { HealthBadge } from "@/components/PartnershipHealth";
import PerformancePeriodForm from "@/components/PerformancePeriodForm";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { amountsText } from "@/lib/commissionLedger";
import {
  chosenPeriod,
  countText,
  PAGE_SIZE,
  PERFORMANCE_PATH,
  PERFORMANCE_READERS,
  PERFORMANCE_URL,
  type PerformancePage,
  periodLabel,
  periodQuery,
} from "@/lib/partnershipPerformance";
import type { User } from "@/lib/types";
import { shellFor, universityPath } from "@/lib/universities";

type Search = { from?: string; to?: string; offset?: string };

// upc-018 (§18, spec §5): the "University Performance" menu -- the universities in the reader's scope ranked by enrolments for a period,
// each with its funnel counts, and a Total row over every ranked university. The period and the page live in the URL (a plain GET form).
export default async function UniversityPerformancePage({ searchParams }: { searchParams: Promise<Search> }) {
  const search = await searchParams;
  const { period, note } = chosenPeriod(search.from, search.to);
  const offset = Math.max(0, Math.floor(Number(search.offset) || 0));
  let user: User;
  let data: PerformancePage;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (!PERFORMANCE_READERS.has(user.role)) return accessDenied(user, "University performance access required");
    data = await serverApi<PerformancePage>(`${PERFORMANCE_URL}?${periodQuery(period, { limit: String(PAGE_SIZE), offset: String(offset) })}`);
  } catch (e) {
    return accessUnavailable(e, "/overseas/login");
  }
  const { nav, roleLabel } = shellFor(user.role);
  const tracked = data.steps.filter((s) => s.tracked);
  const money = data.commission; // upc-019 F10 / F11: sent to the commission roles only
  const pageHref = (to: number) => `${PERFORMANCE_PATH}?${periodQuery(period, { offset: String(to) })}`;
  const last = data.offset + data.items.length;
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">University Performance</div>
            <h2>Partner performance — {periodLabel(period)}</h2>
            <p className="muted">Your universities ranked by students enrolled, then applications. Partners are listed even when nothing happened in the period.</p>
            <PerformancePeriodForm action={PERFORMANCE_PATH} period={period} />
            {note && <p className="muted">{note}</p>}
          </div>
        </div>
        {data.total === 0 ? (
          <p className="empty">No student activity for these universities in this period.</p>
        ) : (
          <>
            <div className="table-scroll" role="region" aria-labelledby="performance-caption" tabIndex={0}>
              <table className="table">
                <caption id="performance-caption" className="visually-hidden">Student counts by university for {periodLabel(period)}, ranked by enrolments</caption>
                <thead>
                  <tr>
                    <th scope="col">#</th>
                    <th scope="col">University</th>
                    <th scope="col">Country</th>
                    <th scope="col">Stage</th>
                    <th scope="col">Health</th>
                    {tracked.map((s) => <th key={s.key} scope="col">{s.label}</th>)}
                    {money && <><th scope="col">Commission expected</th><th scope="col">Commission received</th></>}
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((row) => (
                    <tr key={row.university.id}>
                      <td>{row.rank}</td>
                      <th scope="row"><Link href={universityPath(row.university.id)}>{row.university.name}</Link></th>
                      <td>{row.university.country}</td>
                      <td>{row.university.stage_label}</td>
                      <td>{row.health ? <HealthBadge health={row.health} /> : <span className="muted">Not scored</span>}</td>
                      {tracked.map((s) => <td key={s.key}>{countText(row.counts[s.key])}</td>)}
                      {money && <><td>{amountsText(row.commission?.expected ?? [])}</td><td>{amountsText(row.commission?.received ?? [])}</td></>}
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr>
                    <td />
                    <th scope="row" colSpan={4}>Total</th>
                    {tracked.map((s) => <td key={s.key}>{countText(data.totals[s.key])}</td>)}
                    {money && <><td>{amountsText(money.expected)}</td><td>{amountsText(money.received)}</td></>}
                  </tr>
                </tfoot>
              </table>
            </div>
            {data.total > data.limit && (
              <nav className="actions" aria-label="Pages" style={{ marginTop: 12, alignItems: "center" }}>
                {data.offset > 0 && <Link className="btn ghost small" href={pageHref(Math.max(0, data.offset - data.limit))}>Previous</Link>}
                <span className="muted">{data.offset + 1}–{last} of {data.total}</span>
                {last < data.total && <Link className="btn ghost small" href={pageHref(last)}>Next</Link>}
              </nav>
            )}
          </>
        )}
        <p className="muted" style={{ fontSize: 13 }}>
          Leads, Counselling and Profiles eligible are not tracked: those records have no university link. The Total row adds each university&apos;s figures, so a
          student interested in two universities counts twice. Health is scored as of today, whatever the period, for active partners only.
          {money && " Commission expected counts students enrolled in the period whose commission trigger is met; commission received counts receipts dated in the period. Amounts are per currency (restricted)."}
        </p>
      </div>
    </PortalShell>
  );
}
