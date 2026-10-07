import type { BdmManagerOption } from "@/lib/bdm";
import type { Filters } from "@/lib/bdmPerformance";

// bdm-024 (DEC-SCOPE-111 §6): the controls the performance pages share -- a plain GET form (works without JavaScript) for the period
// and, for super_admin, the team; and the inline failure with "Try again" and "Show this month".
export function PerformanceFilters({ action, filters, period, managers }: {
  action: string; filters: Filters; period: { from: string; to: string } | null; managers?: BdmManagerOption[];
}) {
  return (
    <form method="get" action={action} className="analytics-form">
      {period !== null && (
        <>
          <label>
            <span className="muted" style={{ display: "block" }}>From</span>
            <input type="date" name="from" defaultValue={filters.from ?? period.from} required />
          </label>
          <label>
            <span className="muted" style={{ display: "block" }}>To</span>
            <input type="date" name="to" defaultValue={filters.to ?? period.to} required />
          </label>
        </>
      )}
      {managers && (
        <label style={{ maxWidth: "100%", minWidth: 0 }}>
          <span className="muted" style={{ display: "block" }}>Team</span>
          {/* QA24-01: an option's "name (email)" must not widen the page on a phone */}
          <select name="manager" defaultValue={filters.manager ?? ""} style={{ maxWidth: "100%" }}>
            <option value="">All teams</option>
            {managers.map((m) => <option key={m.id} value={m.id}>{m.full_name} ({m.email})</option>)}
          </select>
        </label>
      )}
      <button type="submit" className="btn secondary small">Show</button>
      {period !== null && <a href={filters.manager ? `${action}?manager=${filters.manager}` : action} className="btn secondary small">This month</a>}
    </form>
  );
}

/** `reset` is the way out (QA24-03: an unreadable team must not trap super_admin); hidden when it is the failing link itself. */
export function PerformanceLoadError({ message, retryHref, reset }: { message: string; retryHref: string; reset: { href: string; label: string } }) {
  return (
    <div className="card" role="alert">
      <p className="form-error">{message}</p>
      <div className="actions">
        <a href={retryHref} className="btn secondary small">Try again</a>
        {reset.href !== retryHref && <a href={reset.href} className="btn secondary small">{reset.label}</a>}
      </div>
    </div>
  );
}

/** Back to this month, or for super_admin's chosen team, to all teams. */
export const resetTo = (path: string, manager: string | undefined) => ({ href: path, label: manager ? "Show all teams" : "Show this month" });
