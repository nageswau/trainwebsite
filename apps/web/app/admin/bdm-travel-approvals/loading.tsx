import PortalShell from "@/components/PortalShell";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

// bdm-010 (§12.2 F4, review I2): shown while the server reads trips waiting on an inactive manager, inside the portal shell (the ENH-020 pattern).
export default function Loading() {
  return (
    <PortalShell nav={SUPER_ADMIN_NAV} roleLabel="Super Administrator" userName="">
      <div className="portal-content" aria-busy="true" aria-label="Loading trips waiting on an inactive manager">
        <div className="card">
          {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton-line" style={{ width: "100%", marginBottom: 12 }} aria-hidden="true" />)}
        </div>
      </div>
    </PortalShell>
  );
}
