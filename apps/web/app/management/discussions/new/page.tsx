import { accessUnavailable } from "@/components/AccessUnavailable";
import DiscussionForm from "@/components/DiscussionForm";
import DiscussionsShell from "@/components/DiscussionsShell";
import { ApiError, serverApi } from "@/lib/api";
import { indiaToday } from "@/lib/bdmTravel";
import type { ManagementMe } from "@/lib/management";
import { DISCUSSIONS_API, type DiscussionOptions } from "@/lib/managementDiscussions";

// mgmt-027 (MD1-MD7): a new discussion. The people come from the API (active staff); it refuses anyone outside the operational tier.
export default async function NewDiscussionPage() {
  let me: ManagementMe;
  let options: DiscussionOptions;
  try {
    [me, options] = await Promise.all([serverApi<ManagementMe>("/api/v1/management/me"), serverApi<DiscussionOptions>(`${DISCUSSIONS_API}/options`)]);
  } catch (e) {
    if (e instanceof ApiError && e.status >= 500) throw e;
    return accessUnavailable(e, "/admin/login");
  }
  return (
    <DiscussionsShell me={me} title="New discussion" intro="Record what was discussed and, if one was reached, the decision. Attachments can be added once it is saved.">
      <DiscussionForm options={options} today={indiaToday()} />
    </DiscussionsShell>
  );
}
