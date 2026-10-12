import { accessUnavailable } from "@/components/AccessUnavailable";
import DiscussionsShell from "@/components/DiscussionsShell";
import ManagementTaskForm from "@/components/ManagementTaskForm";
import { ApiError, serverApi } from "@/lib/api";
import { indiaToday } from "@/lib/bdmTravel";
import type { ManagementMe } from "@/lib/management";
import type { DiscussionOptions } from "@/lib/managementDiscussions";
import { TASKS_API } from "@/lib/managementTasks";

// mgmt-028 (MT1/MT6/MT7): a new task. The owners come from the API (active staff); it refuses anyone outside the operational tier.
export default async function NewTaskPage() {
  let me: ManagementMe;
  let options: DiscussionOptions;
  try {
    [me, options] = await Promise.all([serverApi<ManagementMe>("/api/v1/management/me"), serverApi<DiscussionOptions>(`${TASKS_API}/options`)]);
  } catch (e) {
    if (e instanceof ApiError && e.status >= 500) throw e;
    return accessUnavailable(e, "/admin/login");
  }
  return (
    <DiscussionsShell me={me} section="To-do" title="New task" intro="Give the task an owner, a priority and a deadline. The owner is notified.">
      <ManagementTaskForm options={options} today={indiaToday()} />
    </DiscussionsShell>
  );
}
