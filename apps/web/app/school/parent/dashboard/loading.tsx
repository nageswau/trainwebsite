import PortalShell from "@/components/PortalShell";
import { SCHOOL_NAV } from "@/lib/navigation";

export default function Loading() {
  return (
    <PortalShell nav={SCHOOL_NAV.parent} roleLabel="Parent" userName="">
      <div className="portal-content" aria-busy="true" aria-label="Loading your children">
        <h1>My children</h1>
        <div className="card"><div className="skeleton-line" style={{ marginBottom: 10 }} /><div className="skeleton-line" style={{ width: "60%" }} /></div>
        <div className="card"><div className="skeleton-line" style={{ marginBottom: 10 }} /><div className="skeleton-line" style={{ width: "60%" }} /></div>
      </div>
    </PortalShell>
  );
}
