import { Suspense } from "react";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PlacementsPanel from "@/components/PlacementsPanel";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { PLACEMENTS_URL } from "@/lib/placements";
import { companyShell, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import type { User } from "@/lib/types";

// pob-024 (DEC-SCOPE-432): the placements list. The API is the gate: a role without access gets its 403 message here.
export default async function RecruiterPlacementsPage() {
  let user: User;
  try {
    [user] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi(`${PLACEMENTS_URL}?limit=1`)]);
  } catch (e) {
    return accessUnavailable(e, RECRUITER_SIGN_IN);
  }
  const { nav, roleLabel } = companyShell(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Closure</div>
            <h2>Placements</h2>
            <p className="muted">One record per accepted offer: joining confirmations, owners and the invoice draft created when the candidate joins.</p>
          </div>
        </div>
        <Suspense fallback={<p className="muted" role="status">Loading placements…</p>}>
          <PlacementsPanel />
        </Suspense>
      </div>
    </PortalShell>
  );
}
