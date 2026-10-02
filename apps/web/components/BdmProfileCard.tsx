import { BDM_TYPE_LABEL, statusLabel, type BdmMe } from "@/lib/bdm";

// bdm-001: a BDM's §1 profile as label/value pairs (a <dl>, so assistive tech announces each pair). Read-only.
export default function BdmProfileCard({ me }: { me: BdmMe }) {
  const p = me.bdm_profile;
  const manager = `${p.reporting_manager.full_name}${p.reporting_manager.active ? "" : " (inactive)"}`;
  const rows: [string, string][] = [
    ["Name", me.full_name],
    ["Employee ID", p.employee_id],
    ["Module", BDM_TYPE_LABEL[p.bdm_type]],
    ["Designation", p.designation ?? "—"],
    ["Department", p.department ?? "—"],
    ["Territory", p.territory ?? "—"],
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
