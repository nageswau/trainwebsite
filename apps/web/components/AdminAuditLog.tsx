import Link from "next/link";

import { actorHistoryHref, AUDIT_DIVISIONS, AUDIT_PAGE_SIZE, auditHref, entityHistoryHref, type AuditFilters, type AuditRow } from "@/lib/auditLog";
import { formatDateTimeIn, SCHOOL_TIME_ZONE } from "@/lib/formatDate";

// nehn-042 (DEC-SCOPE-289 A7/A8): the admin Audit log -- a GET form (refresh, back and a shared link keep the filters), the matching
// rows newest first, and Previous/Next. `rows` is one more than a page when a next page exists (lib/auditLog `auditUrl`), and null when
// the read failed or the filters were refused; the form stays so they can be corrected. An entity reference opens that entity's whole
// history and an actor's name everything they did. Metadata is not shown (it may hold personal data); times are India time (IST).
export default function AdminAuditLog({ base, rows, error, filters, showDivision }: {
  base: string; rows: AuditRow[] | null; error: string; filters: AuditFilters; showDivision: boolean;
}) {
  const text = (name: "actor" | "action" | "entity_type" | "entity_id", label: string, hint?: string) => (
    <div className="field" style={{ margin: 0 }}>
      <label htmlFor={`audit-${name}`}>{label}</label>
      <input id={`audit-${name}`} className="input" name={name} defaultValue={filters[name]} placeholder={hint} />
    </div>
  );
  const shown = rows?.slice(0, AUDIT_PAGE_SIZE) ?? [];
  const hasNext = (rows?.length ?? 0) > AUDIT_PAGE_SIZE;

  return (
    <div className="action-card">
      {error && <p className="form-error" role="alert">{error}</p>}
      <form method="get" action={base} aria-label="Audit log filters" className="analytics-form">
        {text("actor", "Done by", "User reference")}
        {text("action", "Action", "e.g. payment.")}
        {text("entity_type", "Entity type", "e.g. payment")}
        {text("entity_id", "Entity reference")}
        {showDivision && (
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor="audit-division">Division</label>
            <select id="audit-division" name="division" defaultValue={filters.division}>
              <option value="">All divisions</option>
              {AUDIT_DIVISIONS.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
            </select>
          </div>
        )}
        {(["date_from", "date_to"] as const).map((name) => (
          <div className="field" style={{ margin: 0 }} key={name}>
            <label htmlFor={`audit-${name}`}>{name === "date_from" ? "From" : "To"}</label>
            <input id={`audit-${name}`} className="input" type="date" name={name} defaultValue={filters[name]} />
          </div>
        ))}
        <button className="btn" type="submit">Apply</button>
        <Link className="btn secondary" href={base}>Clear filters</Link>
      </form>
      {rows && shown.length === 0 && <p className="empty" role="status">No audit records match these filters.</p>}
      {shown.length > 0 && (
        <>
          <div className="table-wrap">
            <table className="table stack compact" aria-label="Audit log">
              <thead><tr><th scope="col">When</th><th scope="col">Done by</th><th scope="col">Action</th><th scope="col">Entity</th><th scope="col">Entity reference</th><th scope="col">Outcome</th></tr></thead>
              <tbody>
                {shown.map((row) => (
                  <tr key={row.id}>
                    <th scope="row" data-label="When"><time dateTime={row.created_at}>{formatDateTimeIn(row.created_at, SCHOOL_TIME_ZONE, true)}</time></th>
                    <td data-label="Done by" style={{ overflowWrap: "anywhere" }}>
                      {row.actor ? <Link href={actorHistoryHref(base, row.actor.id)}>{row.actor.full_name}</Link> : row.user_id ?? "System"}
                    </td>
                    {/* QA-042-01: break-word keeps the column as wide as its longest action, so a name only wraps when it cannot fit at all */}
                    <td data-label="Action" style={{ overflowWrap: "break-word" }}>{row.action}</td>
                    <td data-label="Entity">{row.entity_type}</td>
                    <td data-label="Entity reference" style={{ overflowWrap: "anywhere" }}>
                      {row.entity_id ? <Link href={entityHistoryHref(base, row.entity_type, row.entity_id)}>{row.entity_id}</Link> : "—"}
                    </td>
                    <td data-label="Outcome">{row.outcome}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {(filters.offset > 0 || hasNext) && (
            <nav aria-label="Audit log pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
              <span className="muted" style={{ fontSize: 13 }}>Showing {filters.offset + 1}–{filters.offset + shown.length}</span>
              {filters.offset > 0 && <Link className="btn secondary small" aria-label="Previous page" href={auditHref(base, { ...filters, offset: Math.max(0, filters.offset - AUDIT_PAGE_SIZE) })}>Previous</Link>}
              {hasNext && <Link className="btn secondary small" aria-label="Next page" href={auditHref(base, { ...filters, offset: filters.offset + AUDIT_PAGE_SIZE })}>Next</Link>}
            </nav>
          )}
        </>
      )}
    </div>
  );
}
