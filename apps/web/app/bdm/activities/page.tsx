import { accessUnavailable } from "@/components/AccessUnavailable";
import BdmActivityDay from "@/components/BdmActivityDay";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { BDM_TYPE_LABEL, type BdmMe } from "@/lib/bdm";
import { ACTIVITIES_URL, activityDay, type ActivityDayPage, DAY_PAGE } from "@/lib/bdmActivities";
import { bdmNav } from "@/lib/bdmNav";
import { indiaToday } from "@/lib/bdmTravel";
import { BDM_SIGN_IN } from "@/lib/navigation";

const PATH = "/bdm/activities";

// bdm-009 (spec §6.2): my activities on one IST day with that day's counts. The date lives in the URL (a plain GET form, no JS); a
// malformed or future date is replaced by today, with a note (QA9B-01), so the API is never asked for it.
export default async function MyActivitiesPage({ searchParams }: { searchParams: Promise<{ date?: string }> }) {
  const nav = bdmNav(); // the unread badge, read alongside the page's own data (never rejects)
  const raw = (await searchParams).date;
  const today = indiaToday();
  const { day: chosen, note } = activityDay(raw, today);
  const url = `${ACTIVITIES_URL}?date=${chosen}`;
  let me: BdmMe, day: ActivityDayPage;
  try {
    [me, day] = await Promise.all([serverApi<BdmMe>("/api/v1/bdm/me"), serverApi<ActivityDayPage>(`${url}&limit=${DAY_PAGE}&offset=0`)]);
  } catch (e) {
    return accessUnavailable(e, BDM_SIGN_IN);
  }
  return (
    <PortalShell nav={await nav} roleLabel={`${BDM_TYPE_LABEL[me.bdm_profile.bdm_type]} BDM`} userName={me.full_name}>
      <div className="portal-content">
        {/* A BDM can log from any day's page: backdating is allowed, and the API applies the 7-day rule. */}
        <BdmActivityDay
          key={chosen}
          pageDay={chosen}
          header={
            <>
              <div className="eyebrow">Activities</div>
              <h2>My activities</h2>
              <p className="muted">Calls, WhatsApp messages, emails, visits and meetings you logged. You can change an entry on the day it happened.</p>
              <form className="analytics-form" method="get" action={PATH} aria-label="Choose a day">
                <div className="field">
                  <label htmlFor="activity-date">Day</label>
                  <input id="activity-date" type="date" name="date" defaultValue={chosen} max={today} />
                </div>
                <button className="btn secondary" type="submit">Show</button>
              </form>
              {note && <p className="muted">{note}</p>}
            </>
          }
          initial={day}
          url={url}
          canLog
          orgBasePath="/bdm/organizations"
        />
      </div>
    </PortalShell>
  );
}
