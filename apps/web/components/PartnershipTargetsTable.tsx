import { monthLabel } from "@/lib/bdmTargets";
import { cellText, managerTargetHref, type TeamTargets } from "@/lib/partnershipTargets";

// upc-021 (spec §5): the team comparison -- one row per manager and the team row, each cell "actual / target · achievement".
export default function PartnershipTargetsTable({ team, month }: { team: TeamTargets; month: string }) {
  if (team.managers.length === 0) return <p className="empty">No partnership managers report to you yet.</p>;
  return (
    <div className="table-scroll" role="region" aria-labelledby="team-targets-caption" tabIndex={0}>
      <table className="table">
        <caption id="team-targets-caption" className="visually-hidden">Actual / target and achievement by manager and KPI for {monthLabel(month)}</caption>
        <thead>
          <tr>
            <th scope="col">Manager</th>
            {team.kpis.map((k) => <th key={k.key} scope="col" title={k.definition}>{k.label}</th>)}
            <th scope="col"><span className="visually-hidden">Open</span></th>
          </tr>
        </thead>
        <tbody>
          {team.managers.map((row) => {
            const action = team.editable && row.active ? "Set targets" : "View";
            return (
              <tr key={row.manager.id}>
                <th scope="row">{row.manager.full_name}{!row.active && <span className="kpi-note muted">Inactive</span>}</th>
                {team.kpis.map((k, i) => <td key={k.key}>{cellText(k, row.kpis[i], team.month_status)}</td>)}
                <td>
                  <a className="btn secondary small" href={managerTargetHref(row.manager.id, month)} aria-label={`${action === "View" ? "View" : "Set"} targets for ${row.manager.full_name}`}>{action}</a>
                </td>
              </tr>
            );
          })}
        </tbody>
        <tfoot>
          <tr>
            <th scope="row">Team</th>
            {team.kpis.map((k, i) => <td key={k.key}>{cellText(k, team.team[i], team.month_status)}</td>)}
            <td />
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
