import PortalShell from "@/components/PortalShell";
import SchoolEntitlementsPanel, { type EntitlementsData } from "@/components/SchoolEntitlementsPanel";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";
import { accessUnavailable } from "@/components/AccessUnavailable";

// DEC-SCOPE-017: Principal's read-only Entitlements view -- identical data/scope as the
// Coordinator's own page (GET /school/entitlements already allows both roles).
export default async function SchoolPrincipalEntitlementsPage() {
  let user: User;
  let data: EntitlementsData;
  try {
    [user, data] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<EntitlementsData>("/api/v1/school/entitlements")]);
  } catch (e) {
    return accessUnavailable(e);
  }
  return (
    <PortalShell nav={SCHOOL_NAV.principal} roleLabel="Principal" userName={user.full_name}>
      <SchoolEntitlementsPanel data={data} />
    </PortalShell>
  );
}
