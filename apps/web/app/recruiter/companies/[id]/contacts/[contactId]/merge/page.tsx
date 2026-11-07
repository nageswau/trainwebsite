import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import { RecruiterContactMerge } from "@/components/RecruiterCompanyMerge";
import { serverApi } from "@/lib/api";
import { companyShell, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import type { User } from "@/lib/types";

// pob-006 (DEC-SCOPE-418 C1): merge a duplicate contact of this company into this contact. `crm.merge`; the API checks scope and every rule.
export default async function RecruiterContactMergePage({ params }: { params: Promise<{ id: string; contactId: string }> }) {
  const { id, contactId } = await params;
  let user: User;
  let permissions: string[];
  try {
    const [me, grants] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<{ permissions: string[] }>("/api/v1/auth/me/permissions")]);
    user = me;
    permissions = grants.permissions;
  } catch (e) {
    return accessUnavailable(e, RECRUITER_SIGN_IN);
  }
  const { nav, roleLabel } = companyShell(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        {permissions.includes("crm.merge") ? <RecruiterContactMerge companyId={id} survivorId={contactId} /> : <div className="action-card"><p style={{ margin: 0 }}>Your role cannot merge duplicates. Ask your Team Lead for access.</p></div>}
      </div>
    </PortalShell>
  );
}
