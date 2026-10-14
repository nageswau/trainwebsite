import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import DiscussionsShell from "@/components/DiscussionsShell";
import ManagementMeetingForm from "@/components/ManagementMeetingForm";
import { ApiError, serverApi } from "@/lib/api";
import type { ManagementMe } from "@/lib/management";
import type { DiscussionOptions } from "@/lib/managementDiscussions";
import { MEETINGS_API, MEETINGS_HOME, type MeetingDetail } from "@/lib/managementMeetings";

// mgmt-029 (MM2-MM5, MM7): change a meeting -- retitle, reschedule, move it online, change the participants. A cancelled meeting can't
// be changed (the API says 409), so the page says so instead of offering a form.
export default async function EditMeetingPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let me: ManagementMe;
  let options: DiscussionOptions;
  let meeting: MeetingDetail | null = null;
  try {
    [me, options] = await Promise.all([serverApi<ManagementMe>("/api/v1/management/me"), serverApi<DiscussionOptions>(`${MEETINGS_API}/options`)]);
  } catch (e) {
    if (e instanceof ApiError && e.status >= 500) throw e;
    return accessUnavailable(e, "/admin/login");
  }
  try {
    meeting = await serverApi<MeetingDetail>(`${MEETINGS_API}/${encodeURIComponent(id)}`);
  } catch (e) {
    if (!(e instanceof ApiError && (e.status === 404 || e.status === 422))) throw e;
  }
  if (!meeting || meeting.status === "cancelled") {
    return (
      <DiscussionsShell me={me} section="Meetings" title={meeting ? "Meeting cancelled" : "Meeting not found"}>
        <p className="empty" role="status">
          {meeting ? "This meeting was cancelled; it can't be changed. " : "This meeting does not exist. "}
          <Link className="kpi-link" href={meeting ? `${MEETINGS_HOME}/${meeting.id}` : MEETINGS_HOME}>{meeting ? "Back to the meeting" : "Back to meetings"}</Link>
        </p>
      </DiscussionsShell>
    );
  }
  return (
    <DiscussionsShell me={me} section="Meetings" title={`Edit: ${meeting.title}`}>
      {meeting.status === "completed" && <p className="muted">The minutes are recorded, so the meeting&apos;s date and time can&apos;t change.</p>}
      <ManagementMeetingForm options={options} meeting={meeting} />
    </DiscussionsShell>
  );
}
