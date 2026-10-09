import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import MeetingForm from "@/components/MeetingForm";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import type { PickOption } from "@/lib/lookups";
import { MEETINGS_PATH, SCHEDULER_ROLES } from "@/lib/meetings";
import type { User } from "@/lib/types";
import { shellFor, universityPath } from "@/lib/universities";
import { loadUniversity } from "@/lib/universitiesServer";

// upc-009 (MG15): schedule a meeting. Opened from a university (`?university=<id>`, fixed) or from the meetings list (pick one). A
// partnership manager is responsible for their own meetings; a head may pick a direct report. The API re-checks the scope on save.
export default async function NewMeetingPage({ searchParams }: { searchParams: Promise<{ university?: string }> }) {
  const { university: universityId } = await searchParams;
  let user: User, university: PickOption | null = null, refusal: string | null = null;
  try {
    const [me, uni] = await Promise.all([serverApi<User>("/api/v1/auth/me"), universityId ? loadUniversity(universityId) : Promise.resolve(null)]);
    user = me;
    if (uni) {
      university = { id: uni.id, label: uni.name, detail: `${uni.university_code} · ${[uni.city, uni.country.name].filter(Boolean).join(", ")}` };
      if (!uni.active) refusal = "Reactivate this university before scheduling a meeting with it.";
      else if (!uni.permissions.can_edit_contacts) refusal = "Only the university's partnership managers can schedule a meeting with it.";
    }
  } catch (e) {
    return accessUnavailable(e, "/overseas/login");
  }
  const { nav, roleLabel } = shellFor(user.role);
  const back = universityId ? universityPath(universityId) : MEETINGS_PATH;
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow"><Link href={back}>{universityId ? "University" : "Meetings"}</Link></div>
            <h2>Schedule a university meeting</h2>
            <p className="muted">Scheduling moves the university to Meeting Scheduled when it is at an earlier stage.</p>
          </div>
        </div>
        {SCHEDULER_ROLES.has(user.role) && !refusal ? (
          <MeetingForm university={university} canPickResponsible={user.role === "partnership_head"} />
        ) : (
          <p className="empty" role="status">
            {SCHEDULER_ROLES.has(user.role) ? refusal : "Only partnership managers and heads schedule meetings."}{" "}
            <Link href={back}>Go back</Link>
          </p>
        )}
      </div>
    </PortalShell>
  );
}
