import { Suspense } from "react";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import RecruiterReceivablesPanel from "@/components/RecruiterReceivablesPanel";
import { serverApi } from "@/lib/api";
import { companyShell, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import { INVOICES_URL } from "@/lib/recruiterRevenue";
import type { User } from "@/lib/types";

// rec-031 (spec §4): the receivables list. The API is the gate: a role without access (bdm, hr_team, employer...) or a recruiter
// without a profile gets its 403 message here, from the probe read alongside the session.
export default async function RecruiterReceivablesPage() {
  let user: User;
  try {
    [user] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi(`${INVOICES_URL}?limit=1`)]);
  } catch (e) {
    return accessUnavailable(e, RECRUITER_SIGN_IN);
  }
  const { nav, roleLabel } = companyShell(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Revenue</div>
            <h2>Receivables</h2>
            <p className="muted">Invoices recorded on job requirements and what is still to be received. Record an invoice or a payment from the requirement&apos;s Revenue section.</p>
          </div>
        </div>
        <Suspense fallback={<p className="muted" role="status">Loading invoices…</p>}>
          <RecruiterReceivablesPanel />
        </Suspense>
      </div>
    </PortalShell>
  );
}
