import Link from "next/link";

import {
  DISCUSSIONS_HOME, discussionsHref, formatDay, isOverdue, STATUS_LABEL, statusClass, type Discussion, type DiscussionFilters, type DiscussionPage,
} from "@/lib/managementDiscussions";

// mgmt-027 (MD12): the Pending decisions panel (named person, open or in progress, earliest deadline first) above the discussions list.
// The status filter is a GET form keyed on its own link, so refresh, back and shared links keep it. `data` is null when the read failed;
// the form stays usable.
export default function ManagementDiscussions({ data, pending, error, filters, today }: { data: DiscussionPage | null; pending: Discussion[]; error: string; filters: DiscussionFilters; today: string }) {
  return (
    <>
      {error && <p className="form-error" role="alert">{error}</p>}
      <section aria-labelledby="pending-decisions" className="action-card">
        <h3 id="pending-decisions">Pending decisions</h3>
        {pending.length === 0 ? (
          <p className="empty">No pending decisions.</p>
        ) : (
          <ul style={{ margin: 0, paddingLeft: 0, listStyle: "none", display: "grid", gap: 10 }}>
            {pending.map((item) => (
              <li key={item.id} style={{ overflowWrap: "anywhere" }}>
                <Link className="kpi-link" href={`${DISCUSSIONS_HOME}/${item.id}`}>{item.decision}</Link>
                <div className="muted" style={{ fontSize: 13 }}>
                  {item.responsible?.full_name ?? "—"} · {item.deadline ? `due ${formatDay(item.deadline)}` : "no deadline"} · {STATUS_LABEL[item.status]}
                  {isOverdue(item, today) && <> · <span className="status error">Overdue</span></>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
      <div className="action-card">
        <form key={discussionsHref(filters)} method="get" action={DISCUSSIONS_HOME} aria-label="Discussion filters" className="analytics-form" autoComplete="off">
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor="discussion-status-filter">Status</label>
            <select id="discussion-status-filter" name="status" defaultValue={filters.status}>
              <option value="">Any status</option>
              {Object.entries(STATUS_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </div>
          <button className="btn" type="submit">Apply</button>
          <Link className="btn secondary" href={DISCUSSIONS_HOME}>Clear filter</Link>
        </form>
        {data && (data.items.length === 0 ? (
          <p className="empty" role="status">No discussions match this filter.</p>
        ) : (
          <div className="table-wrap" role="region" aria-label="Discussions" tabIndex={0} style={{ overflowX: "auto" }}>
            <table className="table" style={{ minWidth: 720 }}>
              <caption className="visually-hidden">Discussions, newest first</caption>
              <thead>
                <tr><th scope="col">Date</th><th scope="col">Topic</th><th scope="col">Decision</th><th scope="col">Responsible</th><th scope="col">Deadline</th><th scope="col">Status</th></tr>
              </thead>
              <tbody>
                {data.items.map((item) => (
                  <tr key={item.id}>
                    <td style={{ whiteSpace: "nowrap" }}>{formatDay(item.discussion_date)}</td>
                    <td style={{ overflowWrap: "anywhere" }}>
                      <Link className="kpi-link" href={`${DISCUSSIONS_HOME}/${item.id}`}>{item.topic}</Link>
                      {item.department && <div className="muted" style={{ fontSize: 13 }}>{item.department}</div>}
                    </td>
                    <td style={{ overflowWrap: "anywhere" }}>{item.decision ?? <span className="muted">No decision yet</span>}</td>
                    <td>{item.responsible?.full_name ?? "—"}</td>
                    <td style={{ whiteSpace: "nowrap" }}>{item.deadline ? formatDay(item.deadline) : "—"}</td>
                    <td><span className={statusClass(item.status)}>{STATUS_LABEL[item.status]}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
        {data && data.total > data.limit && (
          <nav aria-label="Discussion pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
            <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
            {data.offset > 0 && <Link className="btn secondary small" aria-label="Previous page" href={discussionsHref({ ...filters, offset: Math.max(0, data.offset - data.limit) })}>Previous</Link>}
            {data.offset + data.limit < data.total && <Link className="btn secondary small" aria-label="Next page" href={discussionsHref({ ...filters, offset: data.offset + data.limit })}>Next</Link>}
          </nav>
        )}
      </div>
    </>
  );
}
