import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import RecruiterDriveDetail from "@/components/RecruiterDriveDetail";
import { ApiError, serverApi } from "@/lib/api";
import { companyShell, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import { type Drive, DRIVES_PATH, driveUrl } from "@/lib/recruiterDrives";
import type { User } from "@/lib/types";

// rec-029: one campus drive. A 404 (unknown, or another recruiter's) or a malformed id (422) is a plain "not found" -- it never says which.
export default async function RecruiterDrivePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let user: User;
  let drive: Drive | null = null;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, RECRUITER_SIGN_IN);
  }
  try {
    drive = await serverApi<Drive>(driveUrl(id));
  } catch (e) {
    if (!(e instanceof ApiError && (e.status === 404 || e.status === 422))) return accessUnavailable(e, RECRUITER_SIGN_IN);
  }
  const { nav, roleLabel } = companyShell(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <p style={{ margin: "0 0 12px" }}><Link href={DRIVES_PATH}>← Back to campus drives</Link></p>
        {drive ? <RecruiterDriveDetail initial={drive} /> : (
          <div className="action-card">
            <h2>Drive not found</h2>
            <p>This campus drive does not exist.</p>
          </div>
        )}
      </div>
    </PortalShell>
  );
}
