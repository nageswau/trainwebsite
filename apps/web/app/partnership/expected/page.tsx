import Link from "next/link";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import ExpectedForecastCards from "@/components/ExpectedForecastCards";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { formatCalendarDate } from "@/lib/formatDate";
import {
  chosenWindow,
  EXPECTED_READERS,
  EXPECTED_URL,
  type ExpectedPage,
  emptyText,
  expectedHref,
  PAGE_SIZE,
  probabilityText,
  WINDOW_TABS,
} from "@/lib/partnershipExpected";
import { TARGETS_PATH } from "@/lib/partnershipTargets";
import type { User } from "@/lib/types";
import { shellFor, universityPath } from "@/lib/universities";

type Search = { window?: string; offset?: string };

// upc-023 (§23-§24, spec §5): the dedicated "Expected University Partnerships" screen, reached from Targets & Forecast. The forecast tiles
// (E1-E3, each with its weighted figure), then the §23 table for one window. Window and page live in the URL; the API is the gate, scopes
// the rows (own / team + unowned / all) and computes every figure. An expected date before today reads "Overdue" in the full list.
export default async function ExpectedPartnershipsPage({ searchParams }: { searchParams: Promise<Search> }) {
  const search = await searchParams;
  const window = chosenWindow(search.window);
  const offset = Math.max(0, Math.floor(Number(search.offset) || 0));
  let user: User;
  let data: ExpectedPage;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (!EXPECTED_READERS.has(user.role)) return accessDenied(user, "Expected partnerships access required");
    data = await serverApi<ExpectedPage>(`${EXPECTED_URL}?${new URLSearchParams({ window, limit: String(PAGE_SIZE), offset: String(offset) })}`);
  } catch (e) {
    return accessUnavailable(e, "/overseas/login");
  }
  const { nav, roleLabel } = shellFor(user.role);
  const tab = WINDOW_TABS.find((t) => t.key === window)!;
  const last = data.offset + data.items.length;
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Targets &amp; Forecast</div>
            <h2>Expected University Partnerships</h2>
            <p className="muted">
              Universities not yet signed, with the date their agreement is expected and how likely it is. The probability follows the partnership stage
              unless a manager has overridden it.
            </p>
            <Link className="btn secondary small" href={TARGETS_PATH}>Back to targets</Link>
          </div>
        </div>
        <ExpectedForecastCards windows={data.windows} undatedCount={data.undated_count} />
        <nav className="actions" aria-label="Expected date window" style={{ flexWrap: "wrap", margin: "16px 0 12px" }}>
          {WINDOW_TABS.map((t) => (
            <Link key={t.key} className={`btn small ${t.key === window ? "" : "secondary"}`} aria-current={t.key === window ? "page" : undefined} href={expectedHref(t.key)}>
              {t.label}{t.key === "undated" ? ` (${data.undated_count})` : ""}
            </Link>
          ))}
        </nav>
        {data.items.length === 0 ? (
          <p className="empty">
            {data.total === 0 ? emptyText(window) : <>This page is past the end of the list. <Link href={expectedHref(window)}>Go to the first page</Link></>}
          </p>
        ) : (
          <>
            <div className="table-scroll" role="region" aria-labelledby="expected-caption" tabIndex={0}>
              <table className="table">
                <caption id="expected-caption" className="visually-hidden">Expected university partnerships — {tab.label}</caption>
                <thead>
                  <tr>
                    <th scope="col">University</th>
                    <th scope="col">Country</th>
                    <th scope="col">Stage</th>
                    <th scope="col">Expected date</th>
                    <th scope="col">Owner</th>
                    <th scope="col">Probability</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((row) => {
                    const date = row.expected_agreement_date;
                    return (
                      <tr key={row.university.id}>
                        <th scope="row"><Link href={universityPath(row.university.id)}>{row.university.name}</Link></th>
                        <td>{row.country}</td>
                        <td>{row.stage_label}</td>
                        <td>
                          {date ? formatCalendarDate(date) : <span className="muted">Not set</span>}
                          {date && date < data.today && <span className="kpi-note status error" style={{ marginLeft: 6 }}>Overdue</span>}
                        </td>
                        <td>{row.owner ? row.owner.full_name : <span className="muted">Unassigned</span>}</td>
                        <td>
                          {probabilityText(row.probability, row.stage_probability, row.override_reason !== null)}
                          {row.override_reason && <span className="kpi-note muted" style={{ display: "block" }}>{row.override_reason}</span>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {data.total > data.limit && (
              <nav className="actions" aria-label="Pages" style={{ marginTop: 12, alignItems: "center" }}>
                {data.offset > 0 && <Link className="btn ghost small" href={expectedHref(window, Math.max(0, data.offset - data.limit))}>Previous</Link>}
                <span className="muted">{data.offset + 1}–{last} of {data.total}</span>
                {last < data.total && <Link className="btn ghost small" href={expectedHref(window, last)}>Next</Link>}
              </nav>
            )}
          </>
        )}
      </div>
    </PortalShell>
  );
}
