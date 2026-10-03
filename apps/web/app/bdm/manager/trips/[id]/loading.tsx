import PortalShell from "@/components/PortalShell";
import { BDM_MANAGER_NAV } from "@/lib/navigation";

// bdm-010 (§12.2 F4, review I2): shown while the server reads the trip, inside the portal shell (the ENH-020 pattern).
export default function Loading() {
  return (
    <PortalShell nav={BDM_MANAGER_NAV} roleLabel="Loading…" userName="">
      <div className="portal-content" aria-busy="true" aria-label="Loading the trip">
        <div className="card">
          {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton-line" style={{ width: "100%", marginBottom: 12 }} aria-hidden="true" />)}
        </div>
      </div>
    </PortalShell>
  );
}
