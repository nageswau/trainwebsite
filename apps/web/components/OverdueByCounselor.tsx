import Link from "next/link";

import { overdueTasksHref, type OverdueByCounselorPage } from "@/lib/counselorTasks";
import { formatDay } from "@/lib/managementDiscussions";
import { REMINDER_RULES_HOME } from "@/lib/reminderRules";

// ccrm-031 (DEC-SCOPE-271, E7/E8): who is behind -- every counselor with overdue tasks or follow-ups, worst first, computed live by the
// API. "Past N days" counts what the escalation rule tells the Overseas Admin about; the link opens that counselor's overdue tasks.
export default function OverdueByCounselor({ data }: { data: OverdueByCounselorPage }) {
  const days = `${data.threshold_days} day${data.threshold_days === 1 ? "" : "s"}`;
  return (
    <section id="overdue" aria-labelledby="overdue-heading" className="workspace">
      <div className="workspace-head">
        <h3 id="overdue-heading" style={{ margin: 0 }}>Overdue by counselor</h3>
        <span className="muted">{data.items.length} counselor{data.items.length === 1 ? "" : "s"} behind</span>
      </div>
      <p className="muted" style={{ margin: "0 0 12px" }}>
        {data.enabled ? `Work overdue by more than ${days} is escalated to every Overseas Admin once.` : "Escalation is switched off."} Change it in{" "}
        <Link href={REMINDER_RULES_HOME}>Reminder rules</Link>.
      </p>
      {data.items.length === 0 ? (
        <p className="empty">No counselor has overdue work.</p>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Counselor</th><th scope="col">Overdue tasks</th><th scope="col">Overdue follow-ups</th>
                <th scope="col">Past {days}</th><th scope="col">Oldest due</th><th scope="col"><span className="visually-hidden">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((row) => (
                <tr key={row.counselor.id}>
                  <th scope="row">{row.counselor.full_name}{row.active ? "" : " (inactive)"}</th>
                  <td>{row.overdue_tasks}</td>
                  <td>{row.overdue_follow_ups}</td>
                  <td>{row.past_threshold ? <strong>{row.past_threshold}</strong> : 0}</td>
                  <td className="no-wrap">{row.oldest_due ? formatDay(row.oldest_due) : "—"}</td>
                  <td>
                    {row.overdue_tasks > 0 && (
                      <Link href={overdueTasksHref(row.counselor.id)} aria-label={`View ${row.counselor.full_name}'s overdue tasks`}>View tasks</Link>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
