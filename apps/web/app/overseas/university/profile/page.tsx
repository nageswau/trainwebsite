import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import UniversityViewPanel from "@/components/UniversityView";
import { serverApi } from "@/lib/api";
import { PORTAL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";
import { NOT_LINKED, type UniversityView, VIEW_REFUSED } from "@/lib/universityView";
import { loadUniversityView } from "@/lib/universityViewServer";

// upc-030 (DEC-SCOPE-161 UV3): a university representative's own university -- profile and active courses. The university comes from
// the server-owned `profile.university_id` (UNI-001); the API refuses any other.

export default async function UniversityRepProfilePage() {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/overseas/login");
  }
  if (user.role !== "university_rep") return accessDenied(user, VIEW_REFUSED);
  const universityId = typeof user.profile?.university_id === "string" ? user.profile.university_id : null;
  let view: UniversityView | null = null;
  if (universityId) {
    try {
      view = await loadUniversityView(universityId);
    } catch (e) {
      return accessUnavailable(e, "/overseas/login");
    }
  }
  return (
    <PortalShell nav={PORTAL_NAV["overseas/university"]} roleLabel="University Representative" userName={user.full_name}>
      <div className="portal-content">
        {view ? <UniversityViewPanel view={view} /> : (
          <div className="portal-title"><div><div className="eyebrow">University profile</div><h2>Your university</h2><p className="muted" role="status">{NOT_LINKED}</p></div></div>
        )}
      </div>
    </PortalShell>
  );
}
