import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import UniversityImportPanel from "@/components/UniversityImportPanel";
import { serverApi } from "@/lib/api";
import type { User } from "@/lib/types";
import { CREATOR_ROLES, shellFor, UNIVERSITIES_PATH } from "@/lib/universities";

// upc-005 (IM8, IM12): import universities from a CSV file. The API is the gate; this only hides the panel from the other read roles.
export default async function ImportUniversitiesPage() {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/overseas/login");
  }
  const { nav, roleLabel } = shellFor(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow"><Link href={UNIVERSITIES_PATH}>University Master</Link></div>
            <h2>Import universities</h2>
            <p className="muted">Load many institutions from one CSV file, with a report for every row.</p>
          </div>
        </div>
        {CREATOR_ROLES.has(user.role) ? (
          <UniversityImportPanel />
        ) : (
          <p className="empty" role="status">Your role cannot import universities. Ask your partnership head.</p>
        )}
      </div>
    </PortalShell>
  );
}
