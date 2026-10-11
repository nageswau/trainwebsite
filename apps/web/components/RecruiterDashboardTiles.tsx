import Link from "next/link";

import { TILES, tileHref, type RecruiterDashboard } from "@/lib/recruiterDashboard";

// rec-032 (EVID-018 §1, Appendix B D1-D14): the fourteen tiles, each opening the list it counts (AC3). `null` = the read failed; the
// quick actions and the skill search still render.
export default function RecruiterDashboardTiles({ dashboard, error }: { dashboard: RecruiterDashboard | null; error?: string }) {
  if (dashboard === null) return <p className="muted" role="status">{error || "Your figures are unavailable right now."}</p>;
  const recruiterId = dashboard.recruiter?.id ?? null;
  const expired = dashboard.tiles.requirements_expired;
  return (
    <ul className="metric-grid tel-tiles rec-tiles" aria-label="Your figures">
      {TILES.map((t) => (
        <li key={t.key}>
          <Link className="metric" href={tileHref(t, recruiterId)}>
            <span>{t.label}</span>
            <strong>{dashboard.tiles[t.key]}</strong>
            <small>{t.key === "requirements_expiring" && expired > 0 ? `${expired} past the deadline` : t.hint}</small>
          </Link>
        </li>
      ))}
    </ul>
  );
}
