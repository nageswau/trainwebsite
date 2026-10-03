import { tripNotFound, travelUnavailable } from "@/components/TravelUnavailable";
import PortalShell from "@/components/PortalShell";
import TripWorkspace from "@/components/TripWorkspace";
import { serverApi } from "@/lib/api";
import { indiaToday, isUuid, type Trip } from "@/lib/bdmTravel";
import { BDM_MANAGER_NAV, SUPER_ADMIN_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

const FALLBACK_NOTE = "This BDM's reporting manager is active and decides this trip. A Super Administrator can decide only while that manager is inactive.";

// bdm-010: a team trip, read-only, with Approve/Reject when the API says this caller decides it (the BDM's manager, or a
// super_admin while that manager is inactive). A super_admin keeps the admin navigation (bdm-001 QA-12) and, on a pending trip
// they can't decide, is told why (QA10-13).
export default async function ManagerTripPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!isUuid(id)) return tripNotFound("/admin/login");
  let user: User, trip: Trip;
  try {
    [user, trip] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<Trip>(`/api/v1/bdm/manager/trips/${id}`)]);
  } catch (e) {
    return travelUnavailable(e, "/admin/login", `/bdm/manager/trips/${id}`);
  }
  const superAdmin = user.role === "super_admin";
  const pending = trip.approval_status === "submitted" && trip.travel_status === "planned";
  return (
    <PortalShell nav={superAdmin ? SUPER_ADMIN_NAV : BDM_MANAGER_NAV} roleLabel={superAdmin ? "Super Administrator" : "BDM Manager"} userName={user.full_name}>
      <div className="portal-content">
        <TripWorkspace initialTrip={trip} view="manager" today={indiaToday()}
          backHref={superAdmin ? "/admin/bdm-travel-approvals" : "/bdm/manager/approvals"} backLabel="Back to approvals"
          note={superAdmin && pending && !trip.can_decide ? FALLBACK_NOTE : undefined} />
      </div>
    </PortalShell>
  );
}
