import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import RecruiterCompanyImport from "@/components/RecruiterCompanyImport";
import { serverApi } from "@/lib/api";
import { COMPANIES_PATH, companyShell, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import type { User } from "@/lib/types";

// pob-006 (DEC-SCOPE-418): the company and contact import. `crm.import`: placement managers by default, an authorised recruiter by a per-user allow.
export default async function RecruiterCompanyImportPage() {
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
        <p style={{ margin: 0 }}><Link href={COMPANIES_PATH}>Back to companies</Link></p>
        <div className="portal-title">
          <div>
            <div className="eyebrow">Companies</div>
            <h2>Import companies</h2>
            <p className="muted">Check a spreadsheet of companies and contacts row by row, then add what is new in one go.</p>
          </div>
        </div>
        {permissions.includes("crm.import") ? <RecruiterCompanyImport /> : <div className="action-card"><p style={{ margin: 0 }}>Your role cannot import companies. Ask your Team Lead for access.</p></div>}
      </div>
    </PortalShell>
  );
}
