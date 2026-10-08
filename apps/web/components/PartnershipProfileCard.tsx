import type { PartnershipMe } from "@/lib/partnership";
import { statusLabel } from "@/lib/telecaller";

// upc-001: a partnership manager's profile as label/value pairs (a <dl>, so assistive tech announces each pair). Read-only; the mobile
// is edited with TelecallerPhoneForm (PU3), everything else by an admin.
export default function PartnershipProfileCard({ me }: { me: PartnershipMe }) {
  const p = me.partnership_profile;
  const head = `${p.reporting_head.full_name}${p.reporting_head.active ? "" : " (inactive)"}`;
  const rows: [string, string][] = [
    ["Name", me.full_name],
    ["Employee ID", p.employee_id],
    ["Mobile", me.phone ?? "—"],
    ["Email", me.email],
    ["Reporting head", head],
    ["Status", statusLabel(me.active)],
  ];
  return (
    <div className="card" style={{ padding: 16 }}>
      <dl style={{ display: "grid", gridTemplateColumns: "minmax(120px, max-content) 1fr", gap: "8px 16px", margin: 0 }}>
        {rows.map(([label, value]) => [
          <dt key={`${label}-t`} className="muted">{label}</dt>,
          <dd key={`${label}-d`} style={{ margin: 0, overflowWrap: "anywhere" }}>{value}</dd>,
        ])}
      </dl>
    </div>
  );
}
