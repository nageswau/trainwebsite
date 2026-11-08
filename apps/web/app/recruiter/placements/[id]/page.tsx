import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PlacementDetail from "@/components/PlacementDetail";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { type Placement, PLACEMENTS_PATH, placementUrl } from "@/lib/placements";
import { companyShell, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import type { User } from "@/lib/types";

// pob-024 (DEC-SCOPE-432): one placement. Out of scope is the API's 404, shown as its message.
export default async function RecruiterPlacementPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let user: User;
  let placement: Placement;
  try {
    const [me, body] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<{ placement: Placement }>(placementUrl(id))]);
    user = me;
    placement = body.placement;
  } catch (e) {
    return accessUnavailable(e, RECRUITER_SIGN_IN);
  }
  const { nav, roleLabel } = companyShell(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow"><Link href={PLACEMENTS_PATH} style={LINK_STYLE}>Placements</Link></div>
            <h2>Placement: {placement.candidate.name}</h2>
            <p className="muted">{placement.role} at {placement.company.name}</p>
          </div>
        </div>
        <PlacementDetail initial={placement} />
      </div>
    </PortalShell>
  );
}
