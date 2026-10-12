import Link from "next/link";

import { formatDateTimeIn, SCHOOL_TIME_ZONE } from "@/lib/formatDate";
import { activityHref, describeActivity, MANAGEMENT_ACTIVITY, MANAGEMENT_ROLE_LABEL, type ActivityFilters, type ManagementActivityPage } from "@/lib/management";

// mgmt-002 (DEC-SCOPE-187 MA5-MA7): who did what in management, newest first. A GET form (as the telecaller reports), so refresh, back
// and a shared link keep the filters. `data` is null when the read failed or the API refused the filters; the form stays to fix them.
// Times are India time on the server and in the browser alike (the date filter's days are IST days too).
export default function ManagementActivity({ data, error, filters }: { data: ManagementActivityPage | null; error: string; filters: ActivityFilters }) {
  const select = (name: "actor" | "kind", label: string, all: string, choices: { value: string; label: string }[]) => (
    <div className="field" style={{ margin: 0 }}>
      <label htmlFor={`activity-${name}`}>{label}</label>
      <select id={`activity-${name}`} name={name} defaultValue={filters[name]}>
        <option value="">{all}</option>
        {/* A value from the address that is not offered stays visible, so the filter shown is the filter applied. */}
        {filters[name] && !choices.some((c) => c.value === filters[name]) && <option value={filters[name]}>{filters[name]}</option>}
        {choices.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
      </select>
    </div>
  );
  const actors = (data?.actors ?? []).map((a) => ({ value: a.id, label: `${a.full_name} (${MANAGEMENT_ROLE_LABEL[a.role] ?? a.role})` }));

  return (
    <div className="action-card">
      {error && <p className="form-error" role="alert">{error}</p>}
      <form method="get" action={MANAGEMENT_ACTIVITY} aria-label="Activity filters" className="analytics-form">
        {select("actor", "Done by", "Everyone", actors)}
        {select("kind", "Kind", "All kinds", data?.kinds ?? [])}
        {(["date_from", "date_to"] as const).map((name) => (
          <div className="field" style={{ margin: 0 }} key={name}>
            <label htmlFor={`activity-${name}`}>{name === "date_from" ? "From" : "To"}</label>
            <input id={`activity-${name}`} className="input" type="date" name={name} defaultValue={filters[name]} />
          </div>
        ))}
        <button className="btn" type="submit">Apply</button>
        <Link className="btn secondary" href={MANAGEMENT_ACTIVITY}>Clear filters</Link>
      </form>
      {data && data.items.length === 0 && <p className="empty" role="status">No management activity matches these filters.</p>}
      {data && data.items.length > 0 && (
        <>
          <ol aria-label="Management activity" style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 8 }}>
            {data.items.map((item) => {
              const { title, detail } = describeActivity(item);
              return (
                <li key={item.id} className="panel" style={{ padding: "12px 16px", overflowWrap: "anywhere" }}>
                  <strong>{title}</strong>
                  {item.entity_id && <span className="muted"> · {item.entity_id}</span>}
                  {detail && <div style={{ fontSize: 14 }}>{detail}</div>}
                  <div className="muted" style={{ fontSize: 13 }}>
                    by {item.actor ? `${item.actor.full_name} (${MANAGEMENT_ROLE_LABEL[item.actor.role] ?? item.actor.role})` : "System"} ·{" "}
                    <time dateTime={item.at}>{formatDateTimeIn(item.at, SCHOOL_TIME_ZONE, true)}</time>
                  </div>
                </li>
              );
            })}
          </ol>
          {data.total > data.limit && (
            <nav aria-label="Activity pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
              <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
              {data.offset > 0 && <Link className="btn secondary small" aria-label="Previous page" href={activityHref({ ...filters, offset: Math.max(0, data.offset - data.limit) })}>Previous</Link>}
              {data.offset + data.limit < data.total && <Link className="btn secondary small" aria-label="Next page" href={activityHref({ ...filters, offset: data.offset + data.limit })}>Next</Link>}
            </nav>
          )}
        </>
      )}
    </div>
  );
}
