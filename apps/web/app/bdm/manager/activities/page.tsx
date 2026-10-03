import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import BdmActivityDay from "@/components/BdmActivityDay";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import { type ActivityDayPage, DAY_PAGE, TEAM_ACTIVITIES_URL } from "@/lib/bdmActivities";
import { bdmManagerNav } from "@/lib/bdmNav";
import { indiaToday, isIsoDate, isUuid } from "@/lib/bdmTravel";
import type { User } from "@/lib/types";

const PATH = "/bdm/manager/activities";

// bdm-009 (spec §6.2): the team's activities on one IST day, optionally for one BDM. Read-only (managers do not log, Q-17).
export default async function ManagerActivitiesPage({ searchParams }: { searchParams: Promise<{ date?: string; bdm?: string }> }) {
  const nav = bdmManagerNav();
  const sp = await searchParams;
  const today = indiaToday();
  const chosen = sp.date && isIsoDate(sp.date) ? sp.date : today;
  const bdm = sp.bdm && isUuid(sp.bdm) ? sp.bdm : null;
  const url = `${TEAM_ACTIVITIES_URL}?date=${chosen}${bdm ? `&bdm_user_id=${bdm}` : ""}`;
  let user: User, team: Page<{ id: string; full_name: string }>, day: ActivityDayPage;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (user.role !== "bdm_manager" && user.role !== "super_admin") return accessDenied(user, "This page is for BDM managers.");
    [team, day] = await Promise.all([
      serverApi<Page<{ id: string; full_name: string }>>("/api/v1/bdm/manager/team?limit=100&offset=0"),
      serverApi<ActivityDayPage>(`${url}&limit=${DAY_PAGE}&offset=0`),
    ]);
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  const chosenName = bdm ? team.items.find((b) => b.id === bdm)?.full_name ?? null : null; // §12.2 F7
  return (
    <PortalShell nav={await nav} roleLabel={user.role === "super_admin" ? "Super Admin" : "BDM Manager"} userName={user.full_name}>
      <div className="portal-content">
        <BdmActivityDay
          key={`${chosen}-${bdm ?? "all"}`}
          pageDay={chosen}
          header={
            <>
              <div className="eyebrow">Activities</div>
              <h2>Team activities</h2>
              <p className="muted">What your BDMs logged on the chosen day, with that day&apos;s counts.</p>
              <form className="analytics-form" method="get" action={PATH} aria-label="Filter activities">
                <div className="field">
                  <label htmlFor="team-activity-date">Day</label>
                  <input id="team-activity-date" type="date" name="date" defaultValue={chosen} max={today} />
                </div>
                <div className="field">
                  <label htmlFor="team-activity-bdm">BDM</label>
                  <select id="team-activity-bdm" name="bdm" defaultValue={bdm ?? ""}>
                    <option value="">Everyone</option>
                    {team.items.map((b) => <option key={b.id} value={b.id}>{b.full_name}</option>)}
                  </select>
                </div>
                <button className="btn secondary" type="submit">Show</button>
              </form>
            </>
          }
          initial={day}
          url={url}
          canLog={false}
          orgBasePath="/bdm/manager/organizations"
          emptyText={chosenName ? `No activities from ${chosenName} on this day.` : "No activities on this day."}
        />
      </div>
    </PortalShell>
  );
}
