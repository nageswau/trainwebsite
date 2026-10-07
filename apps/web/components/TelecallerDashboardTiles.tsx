import { TILES, tileValue, type DashboardTiles } from "@/lib/telecallerMetrics";

// tel-021 (EVID-019 §1, Appendix B B1-B10): today's ten tiles. `null` = the read failed; the rest of the dashboard still renders.
export default function TelecallerDashboardTiles({ tiles }: { tiles: DashboardTiles | null }) {
  if (tiles === null) return <p className="muted" role="status">Today&apos;s figures are unavailable right now.</p>;
  return (
    <ul className="metric-grid tel-tiles" aria-label="Today at a glance">
      {TILES.map((t) => (
        <li key={t.key} className="metric">
          <span>{t.label}</span>
          <strong>{tileValue(tiles, t.key)}</strong>
          <small>{t.hint}</small>
        </li>
      ))}
    </ul>
  );
}
