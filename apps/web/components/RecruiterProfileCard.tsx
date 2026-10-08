import { managerLabel, type RecruiterMe } from "@/lib/recruiter";
import { statusLabel } from "@/lib/telecaller";

const NOT_SET = "Not set yet — contact your administrator";

// rec-001: a recruiter's profile as label/value pairs (a <dl>, like TelecallerProfileCard). A backfilled recruiter has no Employee ID
// or manager until an admin sets them (AC5).
export default function RecruiterProfileCard({ me }: { me: RecruiterMe }) {
  const p = me.recruiter_profile;
  const rows: [string, string][] = [
    ["Name", me.full_name],
    ["Employee ID", p.employee_id ?? NOT_SET],
    ["Mobile", me.phone ?? "—"],
    ["Email", me.email],
    ["Reporting manager", managerLabel(p.reporting_manager) ?? NOT_SET],
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
