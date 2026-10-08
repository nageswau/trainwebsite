import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import VisitTable from "@/components/VisitTable";
import { serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import { PAGE_SIZE, pageOffset } from "@/lib/telecaller";
import type { User } from "@/lib/types";
import { shellFor } from "@/lib/universities";
import { APPROVALS_PATH, VISITS_URL, type VisitRow } from "@/lib/visits";

// upc-010 (VS4): the visits waiting for this caller's decision, oldest first -- a head's team, or (super_admin) the visits whose head
// is inactive or took part. Open one to approve or return it.
export default async function VisitApprovalsPage({ searchParams }: { searchParams: Promise<{ offset?: string }> }) {
  const offset = pageOffset((await searchParams).offset);
  let user: User, queue: Page<VisitRow>;
  try {
    [user, queue] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<Page<VisitRow>>(`${VISITS_URL}/approvals?limit=${PAGE_SIZE}&offset=${offset}`)]);
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  const { nav, roleLabel } = shellFor(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Visit approvals</div>
            <h2>Visits waiting for your approval</h2>
            <p className="muted">
              {user.role === "super_admin"
                ? "Visits whose partnership head is inactive, or is travelling on or planned the visit, come to a super admin."
                : "Visits your partnership managers submitted. Nobody approves a visit they planned or travel on."}
            </p>
          </div>
        </div>
        {queue.total === 0 ? (
          <p className="empty" role="status">Nothing waiting for approval.</p>
        ) : queue.items.length === 0 ? (
          <p className="empty" role="status">This page is past the end of the queue. <Link className="text-link" href={APPROVALS_PATH}>Go to the first page</Link></p>
        ) : (
          <VisitTable page={queue} label="Visits waiting for approval" pageHref={(o) => (o ? `${APPROVALS_PATH}?offset=${o}` : APPROVALS_PATH)} />
        )}
      </div>
    </PortalShell>
  );
}
