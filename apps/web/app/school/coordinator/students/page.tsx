import PortalShell from "@/components/PortalShell";
import SchoolStudentsPanel from "@/components/SchoolStudentsPanel";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";
import { accessUnavailable } from "@/components/AccessUnavailable";
import type { SchoolStudent } from "@/lib/schoolStudents";

// SCH-001: own-institution student roster, add/edit one at a time, link a parent.
export default async function SchoolCoordinatorStudentsPage() {
  let user: User;
  let students: SchoolStudent[];
  try {
    [user, students] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<SchoolStudent[]>("/api/v1/school/students")]);
  } catch (e) {
    return accessUnavailable(e);
  }
  return (
    <PortalShell nav={SCHOOL_NAV.coordinator} roleLabel="School Coordinator" userName={user.full_name}>
      <SchoolStudentsPanel students={students} />
    </PortalShell>
  );
}
