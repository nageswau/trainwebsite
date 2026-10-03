import Link from "next/link";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import { travelUnavailable } from "@/components/TravelUnavailable";
import PortalShell from "@/components/PortalShell";
import TripTable from "@/components/TripTable";
import { serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import { PAGE_SIZE } from "@/lib/bdm";
import type { TripRow } from "@/lib/bdmTravel";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

const PATH = "/admin/bdm-travel-approvals";

// bdm-010 (T3, T8): the fallback approver's queue -- submitted trips whose reporting manager is inactive. The API returns only
// those to a super_admin, and refuses a decision while the manager is active.
export default async function AdminTravelApprovalsPage({ searchParams }: { searchParams: Promise<{ offset?: string }> }) {
  const raw = Number.parseInt((await searchParams).offset ?? "0", 10);
  const offset = Number.isFinite(raw) && raw > 0 ? raw : 0;
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  if (user.role !== "super_admin") return accessDenied(user, "Super Administrator role required");
  let queue: Page<TripRow>;
  try {
    queue = await serverApi<Page<TripRow>>(`/api/v1/bdm/manager/approvals?limit=${PAGE_SIZE}&offset=${offset}`);
  } catch (e) {
    return travelUnavailable(e, "/admin/login", PATH);
  }
  return (
    <PortalShell nav={SUPER_ADMIN_NAV} roleLabel="Super Administrator" userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">BDM travel</div>
            <h2>Approvals waiting on an inactive manager</h2>
            <p className="muted">When a BDM&apos;s reporting manager is inactive, a Super Administrator approves or rejects their trips.</p>
          </div>
        </div>
        {queue.total === 0 ? (
          <p className="empty" role="status">No trips are waiting on an inactive manager.</p>
        ) : queue.items.length === 0 ? (
          <p className="empty" role="status">This page is past the end of the queue. <Link className="text-link" href={PATH}>Go to the first page</Link></p>
        ) : (
          <TripTable page={queue} label="Trips waiting on an inactive manager" basePath={PATH} showBdm detailHref={(id) => `/bdm/manager/trips/${id}`} />
        )}
      </div>
    </PortalShell>
  );
}
