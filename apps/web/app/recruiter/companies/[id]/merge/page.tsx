import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import RecruiterCompanyMerge from "@/components/RecruiterCompanyMerge";
import { serverApi } from "@/lib/api";
import { companyShell, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import type { User } from "@/lib/types";

// pob-006 (DEC-SCOPE-418 M1): merge a duplicate into this company. `crm.merge`; the API checks scope and every rule.
export default async function RecruiterCompanyMergePage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ victim?: string }> }) {
  const { id } = await params;
  const { victim } = await searchParams;
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
        {permissions.includes("crm.merge") ? <RecruiterCompanyMerge survivorId={id} victimCode={victim} /> : <div className="action-card"><p style={{ margin: 0 }}>Your role cannot merge duplicates. Ask your Team Lead for access.</p></div>}
      </div>
    </PortalShell>
  );
}
