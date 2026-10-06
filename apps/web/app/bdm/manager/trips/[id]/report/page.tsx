import PortalShell from "@/components/PortalShell";
import TripReport, { ReportTitle } from "@/components/TripReport";
import { tripNotFound, travelUnavailable } from "@/components/TravelUnavailable";
import { ApiError, serverApi } from "@/lib/api";
import { isUuid, type Trip } from "@/lib/bdmTravel";
import { bdmManagerNav } from "@/lib/bdmNav";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

// bdm-011 (AC3): a team trip's travel report for the BDM's manager (or a super_admin, who keeps the admin navigation as on the trip
// page). Before completion the API's 409 reason is shown with the way back to the trip.
export default async function ManagerTripReportPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!isUuid(id)) return tripNotFound("/admin/login");
  const tripHref = `/bdm/manager/trips/${id}`;
  let user: User;
  let trip: Trip | null = null;
  let notYet: string | null = null;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return travelUnavailable(e, "/admin/login", `${tripHref}/report`);
  }
  try {
    trip = await serverApi<Trip>(`/api/v1/bdm/manager/trips/${id}/report`);
  } catch (e) {
    if (!(e instanceof ApiError && e.status === 409)) return travelUnavailable(e, "/admin/login", `${tripHref}/report`);
    notYet = e.message;
  }
  const superAdmin = user.role === "super_admin";
  return (
    <PortalShell nav={superAdmin ? SUPER_ADMIN_NAV : await bdmManagerNav()} roleLabel={superAdmin ? "Super Administrator" : "BDM Manager"} userName={user.full_name}>
      <div className="portal-content">
        <ReportTitle trip={trip} tripHref={tripHref} />
        {trip ? <TripReport trip={trip} view="manager" /> : <p className="card" role="status">{notYet}</p>}
      </div>
    </PortalShell>
  );
}
