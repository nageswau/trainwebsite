import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import RecruiterRequirementDetail from "@/components/RecruiterRequirementDetail";
import { ApiError, serverApi } from "@/lib/api";
import { companyShell, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import { type Requirement, REQUIREMENTS_PATH, REQUIREMENTS_URL } from "@/lib/recruiterRequirements";
import type { User } from "@/lib/types";

// rec-007: one requirement. A 404 (unknown, or outside the caller's scope) is a plain "not found" -- it never says which.
export default async function RecruiterRequirementPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ created?: string }> }) {
  const { id } = await params;
  const created = (await searchParams).created === "1";
  let user: User;
  let requirement: Requirement | null = null;
  try {
    const [me, read] = await Promise.allSettled([serverApi<User>("/api/v1/auth/me"), serverApi<{ requirement: Requirement }>(`${REQUIREMENTS_URL}/${encodeURIComponent(id)}`)]);
    if (me.status === "rejected") throw me.reason;
    user = me.value;
    if (read.status === "fulfilled") requirement = read.value.requirement;
    else if (!(read.reason instanceof ApiError && (read.reason.status === 404 || read.reason.status === 422))) throw read.reason;
  } catch (e) {
    return accessUnavailable(e, RECRUITER_SIGN_IN);
  }
  const { nav, roleLabel } = companyShell(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        {requirement ? (
          <RecruiterRequirementDetail initial={requirement} created={created} />
        ) : (
          <div className="action-card">
            <h2>Job requirement not found</h2>
            <p>
              <Link href={REQUIREMENTS_PATH}>Back to job requirements</Link>
            </p>
          </div>
        )}
      </div>
    </PortalShell>
  );
}
