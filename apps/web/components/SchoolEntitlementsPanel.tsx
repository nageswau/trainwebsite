import { formatCalendarDate } from "@/lib/formatDate";

export type EntitlementsData = {
  tier: string | null;
  tier_valid_until: string | null;
  services: { key: string; label: string; included: boolean; used: number | boolean | null }[];
};

// DEC-SCOPE-017 (2026-09-15): what this School's partnership tier includes, with a real
// usage count wherever a confirmed module produces one. "Not tracked" (not "0") is shown
// for services with no underlying feature -- the user explicitly confirmed "included =
// unlimited, count usage," so there is never a fabricated cap or a fake zero here.
export default function SchoolEntitlementsPanel({ data }: { data: EntitlementsData }) {
  const tierLabel = data.tier ? data.tier.charAt(0).toUpperCase() + data.tier.slice(1) : null;

  function usedLabel(used: number | boolean | null) {
    if (used === null || used === undefined) return <span className="muted">Not tracked</span>;
    if (typeof used === "boolean") return used ? "Assigned" : "Not assigned";
    return used;
  }

  return (
    <div className="portal-content">
      <div className="card">
        <h2>Partnership entitlements</h2>
        {!data.tier ? (
          <p className="muted">No partnership tier has been set for your school yet. Contact your EduSphere Overseas Admin.</p>
        ) : (
          <>
            <p><strong>Plan:</strong> {tierLabel} Partner{data.tier_valid_until ? ` — valid until ${formatCalendarDate(data.tier_valid_until)}` : ""}</p>
            <div className="table-wrap" style={{ marginTop: 12 }}>
              <table className="table">
                <thead>
                  <tr><th>Service</th><th>Included</th><th>Used</th></tr>
                </thead>
                <tbody>
                  {data.services.map((s) => (
                    <tr key={s.key}>
                      <td>{s.label}</td>
                      <td>✓</td>
                      <td>{usedLabel(s.used)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
