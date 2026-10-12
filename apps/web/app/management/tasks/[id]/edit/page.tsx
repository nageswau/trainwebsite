import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import DiscussionsShell from "@/components/DiscussionsShell";
import ManagementTaskForm from "@/components/ManagementTaskForm";
import { ApiError, serverApi } from "@/lib/api";
import { indiaToday } from "@/lib/bdmTravel";
import type { ManagementMe } from "@/lib/management";
import type { DiscussionOptions } from "@/lib/managementDiscussions";
import { TASKS_API, TASKS_HOME, type ManagementTask } from "@/lib/managementTasks";

// mgmt-028 (MT6-MT8/MT11): change a task -- reassign it (an inactive owner's prompt), re-prioritise, move the deadline, cancel it.
export default async function EditTaskPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let me: ManagementMe;
  let options: DiscussionOptions;
  let task: ManagementTask | null = null;
  try {
    [me, options] = await Promise.all([serverApi<ManagementMe>("/api/v1/management/me"), serverApi<DiscussionOptions>(`${TASKS_API}/options`)]);
  } catch (e) {
    if (e instanceof ApiError && e.status >= 500) throw e;
    return accessUnavailable(e, "/admin/login");
  }
  try {
    task = await serverApi<ManagementTask>(`${TASKS_API}/${encodeURIComponent(id)}`);
  } catch (e) {
    if (!(e instanceof ApiError && (e.status === 404 || e.status === 422))) throw e;
  }
  if (!task) {
    return (
      <DiscussionsShell me={me} section="To-do" title="Task not found">
        <p className="empty" role="status">This task does not exist. <Link className="kpi-link" href={TASKS_HOME}>Back to the to-do</Link></p>
      </DiscussionsShell>
    );
  }
  return (
    <DiscussionsShell me={me} section="To-do" title={`Edit: ${task.title}`}>
      <ManagementTaskForm options={options} today={indiaToday()} task={task} />
    </DiscussionsShell>
  );
}
