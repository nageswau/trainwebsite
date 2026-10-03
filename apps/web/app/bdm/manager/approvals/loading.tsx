import PortalShell from "@/components/PortalShell";
import { BDM_MANAGER_NAV } from "@/lib/navigation";

// bdm-010 (§12.2 F4): shown while the server reads trips waiting for approval, inside the portal shell so the sidebar never flashes away
// (the ENH-020 pattern).
export default function Loading() {
  return (
    <PortalShell nav={BDM_MANAGER_NAV} roleLabel="Loading…" userName="">
      <div className="portal-content" aria-busy="true" aria-label="Loading trips waiting for approval">
        <div className="card">
          {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton-line" style={{ width: "100%", marginBottom: 12 }} aria-hidden="true" />)}
        </div>
      </div>
    </PortalShell>
  );
}
