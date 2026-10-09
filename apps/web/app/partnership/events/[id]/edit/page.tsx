import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PartnershipEventForm from "@/components/PartnershipEventForm";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { eventPath, type PartnershipEvent } from "@/lib/partnershipCalendar";
import { loadEvent } from "@/lib/partnershipEventsServer";
import type { User } from "@/lib/types";
import { shellFor } from "@/lib/universities";

// upc-011 (CL6/CL7): edit a scheduled event -- the owner or the person who added it (the API's `permissions.can_edit`).
export default async function EditEventPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let user: User, e: PartnershipEvent;
  try {
    [user, e] = await Promise.all([serverApi<User>("/api/v1/auth/me"), loadEvent(id)]);
  } catch (err) {
    return accessUnavailable(err, "/overseas/login");
  }
  const { nav, roleLabel } = shellFor(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow"><Link href={eventPath(e.id)}>{e.code}</Link></div>
            <h2>Edit event</h2>
          </div>
        </div>
        {e.permissions.can_edit ? (
          <PartnershipEventForm event={e} canPickOwner={user.role === "partnership_head"} />
        ) : (
          <p className="empty" role="status">
            {e.status === "cancelled" ? "This event was cancelled." : "Only the event's owner or the person who added it can change it."}{" "}
            <Link href={eventPath(e.id)}>Go back</Link>
          </p>
        )}
      </div>
    </PortalShell>
  );
}
