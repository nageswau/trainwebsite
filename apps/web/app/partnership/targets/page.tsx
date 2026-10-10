import Link from "next/link";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import ExpectedForecastCards from "@/components/ExpectedForecastCards";
import PartnershipTargetsTable from "@/components/PartnershipTargetsTable";
import PortalShell from "@/components/PortalShell";
import TargetsEditor from "@/components/TargetsEditor";
import { serverApi } from "@/lib/api";
import { chosenMonth, currentMonth, monthLabel, monthOptions } from "@/lib/bdmTargets";
import { EXPECTED_PATH, EXPECTED_URL, type ExpectedPage } from "@/lib/partnershipExpected";
import {
  type ManagerTargetSheet,
  managerTargetUrl,
  TARGET_READERS,
  TARGETS_PATH,
  TARGETS_URL,
  type TeamTargets,
} from "@/lib/partnershipTargets";
import type { User } from "@/lib/types";
import { shellFor } from "@/lib/universities";

// upc-021 (§21, spec §5): the "Targets & Forecast" menu. A head (or super_admin) compares each manager's month and the team's -- actual /
// target and achievement per KPI -- and opens a manager to set targets. A manager sees their own month, read-only. The month lives in the
// URL (a plain GET form); the API is the gate and computes every figure. upc-023 adds the forecast half (E1-E3 tiles + the expected list).
export default async function PartnershipTargetsPage({ searchParams }: { searchParams: Promise<{ month?: string }> }) {
  const current = currentMonth();
  const { month, note } = chosenMonth((await searchParams).month, current);
  let user: User;
  let team: TeamTargets | null = null;
  let own: ManagerTargetSheet | null = null;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (!TARGET_READERS.has(user.role)) return accessDenied(user, "Partnership targets access required");
    if (user.role === "partnership_manager") own = await serverApi<ManagerTargetSheet>(managerTargetUrl(user.id, month));
    else team = await serverApi<TeamTargets>(`${TARGETS_URL}?month=${month}`);
  } catch (e) {
    return accessUnavailable(e, "/overseas/login");
  }
  // upc-023: the forecast half. Its own read, so a failure here leaves the targets working.
  const forecast = await serverApi<ExpectedPage>(`${EXPECTED_URL}?limit=1`).catch(() => null);
  const { nav, roleLabel } = shellFor(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Targets &amp; Forecast</div>
            <h2>{own ? "My targets" : "Team targets"} — {monthLabel(month)}</h2>
            <p className="muted">
              {own ? "Your monthly targets from your head, and what you achieved." : "Each manager's monthly targets against what they achieved."} Actuals are counted
              by the CRM from university stages, assignments and agreements.
            </p>
            <form className="analytics-form" method="get" action={TARGETS_PATH} aria-label="Choose a month">
              <div className="field">
                <label htmlFor="targets-month">Month</label>
                <select id="targets-month" name="month" defaultValue={month}>
                  {monthOptions(current).map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
                </select>
              </div>
              <button className="btn secondary" type="submit">Show</button>
            </form>
            {note && <p className="muted">{note}</p>}
            {team && !team.editable && <p className="muted">{team.month_status === "past" ? "Past months are read-only." : "Targets can be set up to 12 months ahead."}</p>}
          </div>
        </div>
        {own && <TargetsEditor key={own.month} initial={own} ownerId={own.manager.id} ownerField="manager_user_id" saveUrl={TARGETS_URL} />}
        {team && <PartnershipTargetsTable team={team} month={month} />}
        {team && <p className="muted" style={{ fontSize: 13 }}>Each cell is actual / target · achievement.</p>}
        {forecast ? (
          <>
            <ExpectedForecastCards windows={forecast.windows} undatedCount={forecast.undated_count} />
            <p><Link className="btn secondary small" href={EXPECTED_PATH}>All expected partnerships</Link></p>
          </>
        ) : (
          <p className="form-error">Unable to load the partnership forecast. Reload the page to try again.</p>
        )}
      </div>
    </PortalShell>
  );
}

