import PortalShell from "@/components/PortalShell";
import { SCHOOL_NAV } from "@/lib/navigation";

// ENH-020: shown while the server reads the counsellor's cases, inside the portal shell so the sidebar and header never flash away
// (the dashboard's QA-10 pattern).
export default function Loading() {
  return (
    <PortalShell nav={SCHOOL_NAV["career-counselor"]} roleLabel="Career Counselor" userName="">
      <div className="portal-content" aria-busy="true" aria-label="Loading funding support cases">
        <div className="card">
          {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton-line" style={{ width: "100%", marginBottom: 12 }} aria-hidden="true" />)}
        </div>
      </div>
    </PortalShell>
  );
}
