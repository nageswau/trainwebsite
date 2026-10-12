import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import DiscussionsShell from "@/components/DiscussionsShell";
import ManagementTasks from "@/components/ManagementTasks";
import { ApiError, serverApi } from "@/lib/api";
import type { ManagementMe } from "@/lib/management";
import { TASKS_HOME, taskFilters, tasksUrl, type TaskPage } from "@/lib/managementTasks";

const UNAVAILABLE = "Tasks are unavailable right now. Please try again.";

// mgmt-028 (EVID-017 §28, MT3/MT7): the management to-do in its bands. The API refuses everyone outside the operational tier (the
// accountant included, M13), and the page then shows the access card.
export default async function ManagementTasksPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const filters = taskFilters(await searchParams);
  let me: ManagementMe;
  try {
    me = await serverApi<ManagementMe>("/api/v1/management/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  let data: TaskPage | null = null;
  let error = "";
  try {
    data = await serverApi<TaskPage>(tasksUrl(filters));
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return accessUnavailable(e, "/admin/login");
    error = UNAVAILABLE;
  }
  return (
    <DiscussionsShell me={me} section="To-do" title="Management to-do" actions={<Link className="btn" href={`${TASKS_HOME}/new`}>New task</Link>}
      intro="Tasks for management and staff, each with an owner, priority, deadline and status. Owners see their own tasks in Management tasks.">
      <ManagementTasks data={data} error={error} filters={filters} />
    </DiscussionsShell>
  );
}
