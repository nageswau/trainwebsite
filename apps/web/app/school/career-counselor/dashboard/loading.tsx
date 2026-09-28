import PortalShell from "@/components/PortalShell";
import { SCHOOL_NAV } from "@/lib/navigation";

// ENH-026 (spec §11.2 F5): shown while the server reads the counsellor's records, so navigation is never a blank screen.
// QA-10: rendered inside the portal shell (like the parent pages' loading screen) so the sidebar and header do not flash away.
export default function Loading() {
  return (
    <PortalShell nav={SCHOOL_NAV["career-counselor"]} roleLabel="Career Counselor" userName="">
      <div className="portal-content" aria-busy="true" aria-label="Loading career records">
        <div className="card">
          {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton-line" style={{ width: "100%", marginBottom: 12 }} aria-hidden="true" />)}
        </div>
      </div>
    </PortalShell>
  );
}
