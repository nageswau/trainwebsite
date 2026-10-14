import { accessUnavailable } from "@/components/AccessUnavailable";
import DiscussionsShell from "@/components/DiscussionsShell";
import ManagementMeetingForm from "@/components/ManagementMeetingForm";
import { ApiError, serverApi } from "@/lib/api";
import type { ManagementMe } from "@/lib/management";
import type { DiscussionOptions } from "@/lib/managementDiscussions";
import { MEETINGS_API } from "@/lib/managementMeetings";

// mgmt-029 (MM2-MM5): schedule a management meeting.
export default async function NewMeetingPage() {
  let me: ManagementMe;
  let options: DiscussionOptions;
  try {
    [me, options] = await Promise.all([serverApi<ManagementMe>("/api/v1/management/me"), serverApi<DiscussionOptions>(`${MEETINGS_API}/options`)]);
  } catch (e) {
    if (e instanceof ApiError && e.status >= 500) throw e;
    return accessUnavailable(e, "/admin/login");
  }
  return (
    <DiscussionsShell me={me} section="Meetings" title="New meeting">
      <ManagementMeetingForm options={options} />
    </DiscussionsShell>
  );
}
