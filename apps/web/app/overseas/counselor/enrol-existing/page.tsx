import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import EnrolExistingBody from "@/components/EnrolExistingBody";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { PORTAL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

// ENH-033 (DEC-SCOPE-441 D1): an overseas counselor adds Overseas to an existing IT student.
export default async function OverseasEnrolExistingPage() {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (user.role !== "counselor" || user.division !== "overseas") return accessDenied(user, "Only an overseas counselor or telecaller can enrol a student in Overseas");
  } catch (e) {
    return accessUnavailable(e);
  }
  return (
    <PortalShell nav={PORTAL_NAV["overseas/counselor"]} roleLabel="Counselor" userName={user.full_name}>
      <EnrolExistingBody division="overseas" />
    </PortalShell>
  );
}
