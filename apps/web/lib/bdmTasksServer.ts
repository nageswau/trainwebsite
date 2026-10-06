import { serverApi } from "@/lib/api";
import { isUuid } from "@/lib/bdmTravel";
import { orgTasksUrl, type TaskPage } from "@/lib/bdmTasks";

// Server-only (serverApi reads next/headers). The organization pages' first page of open items, read alongside the organization. It never
// rejects: a failure is null and the section offers "Try again".
export function firstTaskPage(id: string): Promise<TaskPage | null> {
  return isUuid(id) ? serverApi<TaskPage>(orgTasksUrl(id)).catch(() => null) : Promise.resolve(null);
}
