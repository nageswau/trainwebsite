import PortalShell from "@/components/PortalShell";
import { SCHOOL_NAV } from "@/lib/navigation";

// ENH-013 -- skeleton shaped like the header card, the tab list and one panel, so the page does not jump when it loads.
export default function Loading() {
  return (
    <PortalShell nav={SCHOOL_NAV.parent} roleLabel="Parent" userName="">
      <div className="portal-content" aria-busy="true" aria-label="Loading the student 360° view">
        <div className="card"><div className="skeleton-line" style={{ marginBottom: 10 }} /><div className="skeleton-line" style={{ width: "40%" }} /></div>
        <div className="s360-layout">
          <div className="card">{Array.from({ length: 6 }, (_, i) => <div key={i} className="skeleton-line" style={{ marginBottom: 8 }} />)}</div>
          <div className="card"><div className="skeleton-line" style={{ marginBottom: 10 }} /><div className="skeleton-line" /></div>
        </div>
      </div>
    </PortalShell>
  );
}
