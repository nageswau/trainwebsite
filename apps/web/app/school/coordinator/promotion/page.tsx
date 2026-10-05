import PortalShell from "@/components/PortalShell";
import SchoolPromotionPanel from "@/components/SchoolPromotionPanel";
import type { PromotionStudent } from "@/components/SchoolPromotionRow";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";
import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";

type ActiveYear = { id: string; label: string } | null;

// ENH-004: academic-year rollover -- promote or hold back students, own institution only.
// Coordinator-only, like the API (`POST /school/students/promotions` returns 403 for every other role): the role is
// checked here first so a Parent, Teacher or Principal is not shown an action that can only fail, and their roster is
// not fetched for a page they cannot use.
export default async function SchoolCoordinatorPromotionPage() {
  let user: User;
  let students: PromotionStudent[];
  let activeYear: ActiveYear;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (user.role !== "school_coordinator") return accessDenied(user, "School Coordinator role required");
    [students, activeYear] = await Promise.all([
      serverApi<PromotionStudent[]>("/api/v1/school/students"),
      serverApi<ActiveYear>("/api/v1/school/academic-years/active"),
    ]);
  } catch (e) {
    return accessUnavailable(e);
  }
  return (
    <PortalShell nav={SCHOOL_NAV.coordinator} roleLabel="School Coordinator" userName={user.full_name}>
      <SchoolPromotionPanel students={students} activeYear={activeYear} />
    </PortalShell>
  );
}
