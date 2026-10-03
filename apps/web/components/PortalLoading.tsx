import PortalShell from "@/components/PortalShell";
import type { NavItem } from "@/lib/navigation";

// bdm-010 (§12.2 F4, QA10-15): a page's loading skeleton inside the portal shell, so the sidebar never flashes away (the ENH-020
// pattern). The role label is neutral: the page has not read who is signed in yet.
export default function PortalLoading({ nav, label }: { nav: NavItem[]; label: string }) {
  return (
    <PortalShell nav={nav} roleLabel="Loading…" userName="">
      <div className="portal-content" aria-busy="true" aria-label={`Loading ${label}`}>
        <div className="card">
          {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton-line" style={{ width: "100%", marginBottom: 12 }} aria-hidden="true" />)}
        </div>
      </div>
    </PortalShell>
  );
}
