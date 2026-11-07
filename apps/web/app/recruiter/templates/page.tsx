import { Suspense } from "react";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import RecruiterTemplateLibrary from "@/components/RecruiterTemplateLibrary";
import { serverApi } from "@/lib/api";
import { companyShell, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import { TEMPLATES_URL } from "@/lib/recruiterMessages";
import type { User } from "@/lib/types";

// pob-023 (DEC-SCOPE-408, §14): the recruiter's template library -- add, edit and reuse email, LinkedIn, WhatsApp and calling templates.
// A shared template is a draft until the Team Lead approves it; a personal one is only theirs. The API is the gate (the probe's 403).
export default async function RecruiterTemplatesPage() {
  let user: User;
  try {
    [user] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi(`${TEMPLATES_URL}?limit=1`)]);
  } catch (e) {
    return accessUnavailable(e, RECRUITER_SIGN_IN);
  }
  const { nav, roleLabel } = companyShell(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Recruiter CRM</div>
            <h2>Message templates</h2>
            <p className="muted">
              Email, LinkedIn, WhatsApp and calling templates you start from on a company, contact, requirement, candidate or interview. Shared
              templates you add stay drafts until the Team Lead approves them; personal ones are only yours.
            </p>
          </div>
        </div>
        <Suspense fallback={<p className="muted" role="status">Loading templates…</p>}>
          <RecruiterTemplateLibrary approver={user.role === "placement_manager" || user.role === "super_admin"} />
        </Suspense>
      </div>
    </PortalShell>
  );
}
