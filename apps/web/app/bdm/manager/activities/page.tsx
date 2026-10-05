import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import BdmActivityDay from "@/components/BdmActivityDay";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import { activityDay, type ActivityDayPage, DAY_PAGE, TEAM_ACTIVITIES_URL } from "@/lib/bdmActivities";
import { bdmManagerNav } from "@/lib/bdmNav";
import { indiaToday, isUuid, type PersonRef } from "@/lib/bdmTravel";
import type { User } from "@/lib/types";

const PATH = "/bdm/manager/activities";

// bdm-009 (spec §6.2): the team's activities on one IST day, optionally for one BDM. Read-only (managers do not log, Q-17).
export default async function ManagerActivitiesPage({ searchParams }: { searchParams: Promise<{ date?: string; bdm?: string }> }) {
  const nav = bdmManagerNav();
  const sp = await searchParams;
  const today = indiaToday();
  const { day: chosen, note } = activityDay(sp.date, today);
  const wanted = sp.bdm && isUuid(sp.bdm) ? sp.bdm : null;
  let user: User, team: Page<PersonRef>, day: ActivityDayPage, picked: PersonRef | undefined, url: string;
  const dayUrl = (bdmUserId?: string) => `${TEAM_ACTIVITIES_URL}?date=${chosen}${bdmUserId ? `&bdm_user_id=${bdmUserId}` : ""}`;
  const readDay = (query: string) => serverApi<ActivityDayPage>(`${query}&limit=${DAY_PAGE}&offset=0`);
  const readTeam = () => serverApi<Page<PersonRef>>("/api/v1/bdm/manager/team?limit=100&offset=0");
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (user.role !== "bdm_manager" && user.role !== "super_admin") return accessDenied(user, "This page is for BDM managers.");
    if (wanted) {
      team = await readTeam(); // QA9B-05: a BDM outside the team is dropped, not filtered on, so the team is read before the day
      picked = team.items.find((b) => b.id === wanted);
      url = dayUrl(picked?.id);
      day = await readDay(url);
    } else {
      url = dayUrl(); // nothing to check against the team: read both together
      [team, day] = await Promise.all([readTeam(), readDay(url)]);
    }
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  const bdm = picked?.id ?? null;
  const bdmNote = wanted && !picked ? "That BDM isn't in your team — showing everyone." : null;
  const chosenName = picked?.full_name ?? null; // §12.2 F7
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
              {note && <p className="muted">{note}</p>}
              {bdmNote && <p className="muted">{bdmNote}</p>}
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
