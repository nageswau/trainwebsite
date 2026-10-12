import Link from "next/link";

import ManagementTaskBands from "@/components/ManagementTaskBands";
import { formatDay, roleLabel, STATUS_LABEL, statusClass } from "@/lib/managementDiscussions";
import { PRIORITY_LABEL, priorityClass, TASKS_HOME, tasksHref, VIEWS, type TaskFilters, type TaskPage } from "@/lib/managementTasks";

// mgmt-028 (EVID-017 §28, MT3/MT6/MT7): the management to-do -- My tasks (the §28 list), Everyone, or Cancelled -- in bands. Each view is
// its own link, so refresh, back and shared links keep it. `data` is null when the read failed; the views stay usable.
export default function ManagementTasks({ data, error, filters }: { data: TaskPage | null; error: string; filters: TaskFilters }) {
  return (
    <>
      <nav aria-label="Task views" className="actions" style={{ marginBottom: 14 }}>
        {VIEWS.map(({ view, label }) => (
          <Link key={view} className={filters.view === view ? "btn small" : "btn secondary small"} aria-current={filters.view === view ? "page" : undefined} href={tasksHref({ view })}>{label}</Link>
        ))}
      </nav>
      {error && <p className="form-error" role="alert">{error}</p>}
      {data && (
        <ManagementTaskBands items={data.items} empty="No tasks here." renderItem={(task) => (
          <>
            <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", gap: 8 }}>
              <strong>{task.title}</strong>
              <Link className="kpi-link" href={`${TASKS_HOME}/${task.id}/edit`} aria-label={`Edit ${task.title}`}>Edit</Link>
            </div>
            <div className="muted" style={{ fontSize: 14, display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
              <span>{task.owner.full_name} ({roleLabel(task.owner.role)})</span>
              <span>· Due {formatDay(task.deadline)}</span>
              <span className={priorityClass(task.priority)}>{PRIORITY_LABEL[task.priority]} priority</span>
              <span className={statusClass(task.status)}>{STATUS_LABEL[task.status]}</span>
            </div>
            {!task.owner_active && <p style={{ margin: 0 }}><span className="status error">Owner inactive — reassign</span></p>}
          </>
        )} />
      )}
      {data && data.total > data.items.length && <p className="muted" style={{ fontSize: 13 }}>Showing the first {data.items.length} of {data.total} tasks.</p>}
    </>
  );
}
