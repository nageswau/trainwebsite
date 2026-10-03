import Link from "next/link";

import { travelUnavailable } from "@/components/TravelUnavailable";
import PortalShell from "@/components/PortalShell";
import TripTable from "@/components/TripTable";
import { serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import { PAGE_SIZE } from "@/lib/bdm";
import type { TripRow } from "@/lib/bdmTravel";
import { BDM_MANAGER_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

const PATH = "/bdm/manager/approvals";

// bdm-010 (Q-05): trips your BDMs submitted, oldest first. Open one to approve or reject it.
export default async function ManagerApprovalsPage({ searchParams }: { searchParams: Promise<{ offset?: string }> }) {
  const raw = Number.parseInt((await searchParams).offset ?? "0", 10);
  const offset = Number.isFinite(raw) && raw > 0 ? raw : 0;
  let user: User, queue: Page<TripRow>;
  try {
    [user, queue] = await Promise.all([
      serverApi<User>("/api/v1/auth/me"),
      serverApi<Page<TripRow>>(`/api/v1/bdm/manager/approvals?limit=${PAGE_SIZE}&offset=${offset}`),
    ]);
  } catch (e) {
    return travelUnavailable(e, "/admin/login", PATH);
  }
  return (
    <PortalShell nav={BDM_MANAGER_NAV} roleLabel="BDM Manager" userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Approvals</div>
            <h2>Travel waiting for your approval</h2>
            <p className="muted">Every trip needs your approval before it starts. A rejection needs a reason, which the BDM sees.</p>
          </div>
        </div>
        {queue.total === 0 ? (
          <p className="empty" role="status">Nothing waiting for approval.</p>
        ) : queue.items.length === 0 ? (
          <p className="empty" role="status">This page is past the end of the queue. <Link href={PATH}>Go to the first page</Link></p>
        ) : (
          <TripTable page={queue} label="Trips waiting for approval" basePath={PATH} showBdm detailHref={(id) => `/bdm/manager/trips/${id}`} />
        )}
      </div>
    </PortalShell>
  );
}
