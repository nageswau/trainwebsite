import PortalShell from "@/components/PortalShell";
import SchoolActivitiesPanel from "@/components/SchoolActivitiesPanel";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";
import { accessUnavailable } from "@/components/AccessUnavailable";

type Activity = { id: string; title: string; scheduled_at: string };
type Student = { id: string; full_name: string };

// SCH-001: schedule an activity, mark attendance -- for the Coordinator's own institution.
export default async function SchoolCoordinatorActivitiesPage() {
  let user: User;
  let activities: Activity[];
  let students: Student[];
  try {
    [user, activities, students] = await Promise.all([
      serverApi<User>("/api/v1/auth/me"),
      serverApi<Activity[]>("/api/v1/school/activities"),
      serverApi<Student[]>("/api/v1/school/students"),
    ]);
  } catch (e) {
    return accessUnavailable(e);
  }
  return (
    <PortalShell nav={SCHOOL_NAV.coordinator} roleLabel="School Coordinator" userName={user.full_name}>
      <SchoolActivitiesPanel activities={activities} students={students} />
    </PortalShell>
  );
}
