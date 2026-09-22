import PortalShell from "@/components/PortalShell";
import SchoolStudentsPanel from "@/components/SchoolStudentsPanel";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";
import { accessUnavailable } from "@/components/AccessUnavailable";

type Student = { id: string; student_code: string; full_name: string; date_of_birth: string | null; grade_or_class: string | null; academic_year_id: string | null; grade_level: number | null; assigned_teacher_user_id: string | null; pending_parent_email: string | null };

// SCH-001: own-institution student roster, add/edit one at a time, link a parent.
export default async function SchoolCoordinatorStudentsPage() {
  let user: User;
  let students: Student[];
  try {
    [user, students] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<Student[]>("/api/v1/school/students")]);
  } catch (e) {
    return accessUnavailable(e);
  }
  return (
    <PortalShell nav={SCHOOL_NAV.coordinator} roleLabel="School Coordinator" userName={user.full_name}>
      <SchoolStudentsPanel students={students} />
    </PortalShell>
  );
}
