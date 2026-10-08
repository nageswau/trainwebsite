import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import UniversityForm from "@/components/UniversityForm";
import { serverApi } from "@/lib/api";
import type { User } from "@/lib/types";
import { CREATOR_ROLES, shellFor, UNIVERSITIES_PATH } from "@/lib/universities";

// upc-003 (UM8): add a university. It starts internal (not in the public catalogue) until someone publishes it.
export default async function NewUniversityPage() {
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
            <h2>Add university</h2>
            <p className="muted">New universities stay internal until they are published to the catalogue.</p>
          </div>
        </div>
        {CREATOR_ROLES.has(user.role) ? (
          <UniversityForm />
        ) : (
          <p className="empty" role="status">Your role cannot add universities. Ask your partnership head.</p>
        )}
      </div>
    </PortalShell>
  );
}
