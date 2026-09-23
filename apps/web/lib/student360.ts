import { serverApi } from "@/lib/api";
import type { TabKey } from "@/lib/student360Links";

// ENH-013 -- server-only loader and response types for GET /school/students/{id}/360-view (spec §6.1). serverApi fetches with
// cache: "no-store"; never use publicApi here -- it caches for 60s, which would serve one viewer's student record to another.

export type TabStatus = "has_data" | "empty" | "restricted";
export type Tab360<D = Record<string, unknown>> = { status: TabStatus; count: number | null; not_tracked: string[]; data: D };
export type Student360Header = {
  id: string; full_name: string; school_name: string | null; student_code: string | null;
  grade_or_class: string | null; date_of_birth: string | null; assigned_teacher_name: string | null;
};
export type Student360 = { student: Student360Header; career_goal: string | null; can_edit_career_goal: boolean; tabs: Record<TabKey, Tab360> };

export function loadStudent360(studentId: string): Promise<Student360> {
  return serverApi<Student360>(`/api/v1/school/students/${studentId}/360-view`);
}
