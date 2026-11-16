import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import EnrolExistingBody from "@/components/EnrolExistingBody";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { PORTAL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

// ENH-033 (DEC-SCOPE-441 D1): an IT counselor adds IT to an existing Overseas student.
export default async function ItEnrolExistingPage() {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (user.role !== "counselor" || user.division !== "it") return accessDenied(user, "Only an IT counselor or telecaller can enrol a student in IT");
  } catch (e) {
    return accessUnavailable(e, "/it/login");
  }
  return (
    <PortalShell nav={PORTAL_NAV["it/counselor"]} roleLabel="Counselor" userName={user.full_name}>
      <EnrolExistingBody division="it" />
    </PortalShell>
  );
}
