import PortalShell from "@/components/PortalShell";
import { SCHOOL_NAV } from "@/lib/navigation";

export default function Loading() {
  return (
    <PortalShell nav={SCHOOL_NAV.parent} roleLabel="Parent" userName="">
      <div className="portal-content" aria-busy="true" aria-label="Loading this child's profile">
        <div className="card"><div className="skeleton-line" style={{ marginBottom: 10 }} /><div className="skeleton-line" style={{ width: "40%" }} /></div>
      </div>
    </PortalShell>
  );
}
