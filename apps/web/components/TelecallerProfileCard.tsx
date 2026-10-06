import { TEAM_LABEL, statusLabel, type TelecallerMe } from "@/lib/telecaller";

// tel-001: a telecaller's profile as label/value pairs (a <dl>, so assistive tech announces each pair). Read-only; the mobile is
// edited with TelecallerPhoneForm (TL3), everything else by an admin.
export default function TelecallerProfileCard({ me }: { me: TelecallerMe }) {
  const p = me.telecaller_profile;
  const manager = `${p.reporting_manager.full_name}${p.reporting_manager.active ? "" : " (inactive)"}`;
  const rows: [string, string][] = [
    ["Name", me.full_name],
    ["Employee ID", p.employee_id],
    ["Team", TEAM_LABEL[p.team]],
    ["Mobile", me.phone ?? "—"],
    ["Email", me.email],
    ["Reporting manager", manager],
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
