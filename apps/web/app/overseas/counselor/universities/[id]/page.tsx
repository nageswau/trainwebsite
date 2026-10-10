import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import UniversityViewPanel from "@/components/UniversityView";
import { serverApi } from "@/lib/api";
import { PORTAL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";
import { COUNSELOR_UNIVERSITIES_PATH, type UniversityView } from "@/lib/universityView";
import { loadUniversityView } from "@/lib/universityViewServer";

// upc-030 (DEC-SCOPE-161): a counselor's University 360 view. The API is the gate (role, published + active, the slice).
export default async function CounselorUniversityPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let user: User, view: UniversityView;
  try {
    [user, view] = await Promise.all([serverApi<User>("/api/v1/auth/me"), loadUniversityView(id)]);
  } catch (e) {
    return accessUnavailable(e, "/overseas/login");
  }
  return (
    <PortalShell nav={PORTAL_NAV["overseas/counselor"]} roleLabel="Counselor" userName={user.full_name}>
      <div className="portal-content">
        <p style={{ margin: "0 0 8px" }}><Link href={COUNSELOR_UNIVERSITIES_PATH}>← All universities</Link></p>
        <UniversityViewPanel view={view} />
      </div>
    </PortalShell>
  );
}
