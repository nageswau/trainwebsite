import PortalShell from "@/components/PortalShell";
import SchoolTransfersPanel from "@/components/SchoolTransfersPanel";
import { serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { TransferRequest } from "@/lib/transfers";
import type { User } from "@/lib/types";

function AccessUnavailable({ message }: { message: string }) {
  return (
    <div className="section">
      <div className="container card">
        <h1>Access unavailable</h1>
        <p>{message}</p>
        <a className="btn" href="/overseas/login">Return to login</a>
      </div>
    </div>
  );
}

// ENH-005: the coordinator's own transfer requests. Coordinator-only, like the API (every route under /school/transfer-requests answers 403 to
// any other role): the role is checked here first so nobody else is shown a screen that can only fail. The first page (pending) is read on
// the server, so first paint has no spinner and no client round-trip.
export default async function SchoolCoordinatorTransfersPage() {
  let user: User;
  let initial: Page<TransferRequest>;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (user.role !== "school_coordinator") return <AccessUnavailable message="School Coordinator role required" />;
    initial = await serverApi<Page<TransferRequest>>("/api/v1/school/transfer-requests?status=pending&limit=25&offset=0");
  } catch (e) {
    return <AccessUnavailable message={e instanceof Error ? e.message : "Unable to load this workspace"} />;
  }
  return (
    <PortalShell nav={SCHOOL_NAV.coordinator} roleLabel="School Coordinator" userName={user.full_name}>
      <SchoolTransfersPanel initial={initial} />
    </PortalShell>
  );
}
