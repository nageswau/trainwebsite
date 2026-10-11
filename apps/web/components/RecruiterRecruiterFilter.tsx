import { DASHBOARD_PATH } from "@/lib/recruiterDashboard";

// rec-032 (DB3): a manager or super_admin narrows the dashboard to one recruiter. A plain GET form (works without JS; refresh and Back
// keep it); keyed and `autoComplete="off"` so a client navigation or Chrome's form restore never shows a stale choice.
export default function RecruiterRecruiterFilter({ team, selected }: { team: { id: string; full_name: string }[]; selected: string }) {
  return (
    <form key={selected} action={DASHBOARD_PATH} method="get" autoComplete="off" className="actions" style={{ alignItems: "end", flexWrap: "wrap", marginBottom: 16 }}>
      <div className="field" style={{ minWidth: "min(16rem, 100%)" }}>
        <label htmlFor="dashboard-recruiter">Recruiter</label>
        <select id="dashboard-recruiter" name="recruiter" defaultValue={selected}>
          <option value="">Whole team</option>
          {team.map((r) => (
            <option key={r.id} value={r.id}>{r.full_name}</option>
          ))}
        </select>
      </div>
      <button className="btn secondary" type="submit">Show</button>
    </form>
  );
}
