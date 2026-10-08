import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import RecruiterCompanyDetail from "@/components/RecruiterCompanyDetail";
import { ApiError, serverApi } from "@/lib/api";
import { type Company, COMPANIES_PATH, COMPANIES_URL, companyShell, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import type { Page } from "@/lib/apiErrors";
import type { StageEvent } from "@/lib/recruiterPipeline";
import { historyUrl } from "@/lib/recruiterPipeline";
import type { User } from "@/lib/types";

// rec-003: one company. A 404 (unknown, or outside the caller's scope) is a plain "not found" -- it never says which.
export default async function RecruiterCompanyPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ created?: string }> }) {
  const { id } = await params;
  const created = (await searchParams).created === "1";
  let user: User;
  let company: Company | null = null;
  let history: Page<StageEvent> | null = null;
  try {
    const [me, read, events] = await Promise.allSettled([
      serverApi<User>("/api/v1/auth/me"),
      serverApi<{ company: Company }>(`${COMPANIES_URL}/${encodeURIComponent(id)}`),
      serverApi<Page<StageEvent>>(historyUrl(encodeURIComponent(id))), // rec-005: a failure shows "Try again", never blocks the page
    ]);
    if (me.status === "rejected") throw me.reason;
    user = me.value;
    if (read.status === "fulfilled") company = read.value.company;
    else if (!(read.reason instanceof ApiError && (read.reason.status === 404 || read.reason.status === 422))) throw read.reason;
    if (events.status === "fulfilled") history = events.value;
  } catch (e) {
    return accessUnavailable(e, RECRUITER_SIGN_IN);
  }
  const { nav, roleLabel } = companyShell(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        {company ? (
          <RecruiterCompanyDetail initial={company} created={created} history={history} />
        ) : (
          <div className="action-card">
            <h2>Company not found</h2>
            <p>
              <Link href={COMPANIES_PATH}>Back to companies</Link>
            </p>
          </div>
        )}
      </div>
    </PortalShell>
  );
}
