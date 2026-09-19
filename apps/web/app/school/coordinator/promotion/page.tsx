import PortalShell from "@/components/PortalShell";
import SchoolPromotionPanel from "@/components/SchoolPromotionPanel";
import type { PromotionStudent } from "@/components/SchoolPromotionRow";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

type ActiveYear = { id: string; label: string } | null;

// ENH-004: academic-year rollover -- promote or hold back students, own institution only.
export default async function SchoolCoordinatorPromotionPage() {
  let user: User;
  let students: PromotionStudent[];
  let activeYear: ActiveYear;
  try {
    [user, students, activeYear] = await Promise.all([
      serverApi<User>("/api/v1/auth/me"),
      serverApi<PromotionStudent[]>("/api/v1/school/students"),
      serverApi<ActiveYear>("/api/v1/school/academic-years/active"),
    ]);
  } catch (e) {
    return (
      <div className="section">
        <div className="container card">
          <h1>Access unavailable</h1>
          <p>{e instanceof Error ? e.message : "Unable to load this workspace"}</p>
          <a className="btn" href="/overseas/login">Return to login</a>
        </div>
      </div>
    );
  }
  return (
    <PortalShell nav={SCHOOL_NAV.coordinator} roleLabel="School Coordinator" userName={user.full_name}>
      <SchoolPromotionPanel students={students} activeYear={activeYear} />
    </PortalShell>
  );
}
