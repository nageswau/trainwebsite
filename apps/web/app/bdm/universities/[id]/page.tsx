import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import UniversityViewPanel from "@/components/UniversityView";
import { serverApi } from "@/lib/api";
import { bdmManagerNav, bdmNav } from "@/lib/bdmNav";
import { BDM_SIGN_IN } from "@/lib/navigation";
import type { User } from "@/lib/types";
import { type UniversityView, universityViewUrl } from "@/lib/universityView";

// upc-030 (DEC-SCOPE-161 UV6, U13): the University Master record a BDM's university organisation links to -- read-only profile,
// partnership stage and the partnership manager. The API is the gate.
export default async function BdmUniversityPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let user: User, view: UniversityView;
  try {
    [user, view] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<UniversityView>(universityViewUrl(id))]);
  } catch (e) {
    return accessUnavailable(e, BDM_SIGN_IN);
  }
  const manager = user.role === "bdm_manager";
  return (
    <PortalShell nav={await (manager ? bdmManagerNav() : bdmNav())} roleLabel={manager ? "BDM Manager" : "BDM"} userName={user.full_name}>
      <div className="portal-content">
        <UniversityViewPanel view={view} />
      </div>
    </PortalShell>
  );
}
