import PortalShell from "@/components/PortalShell";
import SchoolBulkUploadPanel from "@/components/SchoolBulkUploadPanel";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

// SCH-002: template-download-first bulk roster upload. Entry points are SCR-SCH-002/003
// (the dashboard and roster pages), not a standalone top-level nav item.
export default async function SchoolCoordinatorBulkUploadPage() {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return (
      <div className="section">
        <div className="container card">
          <h1>Access unavailable</h1>
          <p>{e instanceof Error ? e.message : "Unable to load this workspace"}</p>
          <a className="btn" href="/overseas/login">Return to login</a>
        </div>
      </div>
    );
  }
  return (
    <PortalShell nav={SCHOOL_NAV.coordinator} roleLabel="School Coordinator" userName={user.full_name}>
      <SchoolBulkUploadPanel />
    </PortalShell>
  );
}
