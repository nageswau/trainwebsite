import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import MeetingForm from "@/components/MeetingForm";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { type Meeting, meetingPath } from "@/lib/meetings";
import { loadMeeting } from "@/lib/meetingsServer";
import type { User } from "@/lib/types";
import { shellFor } from "@/lib/universities";

// upc-009 (MG9): edit or reschedule a scheduled meeting -- its responsible employee or the person who scheduled it (`can_edit`).
export default async function EditMeetingPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let user: User, m: Meeting;
  try {
    [user, m] = await Promise.all([serverApi<User>("/api/v1/auth/me"), loadMeeting(id)]);
  } catch (e) {
    return accessUnavailable(e, "/overseas/login");
  }
  const { nav, roleLabel } = shellFor(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow"><Link href={meetingPath(m.id)}>{m.code}</Link></div>
            <h2>Edit meeting with {m.university.name}</h2>
            <p className="muted">A new date or time is recorded as a reschedule, with the old and new times.</p>
          </div>
        </div>
        {m.permissions.can_edit ? (
          <MeetingForm meeting={m} canPickResponsible={user.role === "partnership_head"} />
        ) : (
          <p className="empty" role="status">
            {m.status === "scheduled" ? "Only the meeting's responsible employee or the person who scheduled it can change it." : "This meeting can no longer be changed."}{" "}
            <Link href={meetingPath(m.id)}>Back to the meeting</Link>
          </p>
        )}
      </div>
    </PortalShell>
  );
}
