import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PartnershipEventForm from "@/components/PartnershipEventForm";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { CALENDAR_PATH, EVENT_CREATORS } from "@/lib/partnershipCalendar";
import type { User } from "@/lib/types";
import { shellFor } from "@/lib/universities";

// upc-011 (CL2-CL7): add a partnership event. A partnership manager owns their own events; a head may pick a direct report. The API
// re-checks every rule on save.
export default async function NewEventPage() {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/overseas/login");
  }
  const { nav, roleLabel } = shellFor(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow"><Link href={CALENDAR_PATH}>Calendar</Link></div>
            <h2>Add a partnership event</h2>
            <p className="muted">Conferences, education fairs, partner meetings, MoU signings, webinars and university presentations. University meetings and visits are added from their own pages.</p>
          </div>
        </div>
        {EVENT_CREATORS.has(user.role) ? (
          <PartnershipEventForm canPickOwner={user.role === "partnership_head"} />
        ) : (
          <p className="empty" role="status">Only partnership managers and heads add events. <Link href={CALENDAR_PATH}>Go back</Link></p>
        )}
      </div>
    </PortalShell>
  );
}
