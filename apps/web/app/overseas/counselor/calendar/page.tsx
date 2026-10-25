import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import CounselorCalendarFeed from "@/components/CounselorCalendarFeed";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { CALENDAR_FEED_API, type CalendarFeedStatus } from "@/lib/counselorCalendar";
import { PORTAL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

// ccrm-038 (DEC-SCOPE-272 CA4-CA7): the overseas counselor's calendar feed. Unauthenticated users are redirected by the middleware.
const REFUSED = "Only an overseas counselor has a calendar feed";

export default async function CounselorCalendarPage() {
  let user: User, feed: CalendarFeedStatus;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (user.role !== "counselor" || user.division !== "overseas") return accessDenied(user, REFUSED);
    feed = await serverApi<CalendarFeedStatus>(CALENDAR_FEED_API);
  } catch (e) {
    return accessUnavailable(e);
  }
  return (
    <PortalShell nav={PORTAL_NAV["overseas/counselor"]} roleLabel="Counselor" userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Workspace</div>
            <h2>Calendar</h2>
            <p className="muted">Appointment emails carry a calendar invite (.ics). Add the feed below to see every appointment in your own calendar.</p>
          </div>
        </div>
        <CounselorCalendarFeed initial={feed} />
      </div>
    </PortalShell>
  );
}
