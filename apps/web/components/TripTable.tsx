import Link from "next/link";

import type { Page } from "@/lib/apiErrors";
import { APPROVAL_LABEL, MODE_LABEL, TRAVEL_LABEL, formatInr, type TripRow } from "@/lib/bdmTravel";
import { formatCalendarDate } from "@/lib/formatDate";

// bdm-010: a page of trips (the BDM's own, a manager's team, or an approval queue). Server-rendered like BdmTeamTable: paging is a
// link that keeps the filter (`query`) and the offset in the URL. Statuses are words, never colour alone (F9).
export default function TripTable({ page, label, basePath, detailHref, query = "", showBdm = false }: {
  page: Page<TripRow>; label: string; basePath: string; detailHref: (id: string) => string; query?: string; showBdm?: boolean;
}) {
  const end = page.offset + page.items.length;
  const href = (offset: number) => `${basePath}?${query ? `${query}&` : ""}offset=${offset}`;
  return (
    <>
      <div className="table-wrap" role="region" aria-label={label} tabIndex={0}>
        <table>
          <caption className="visually-hidden">{label}</caption>
          <thead>
            <tr>
              {/* QA10-12: Status right after Trip, so a phone shows it before the table scrolls sideways */}
              <th scope="col">Trip</th><th scope="col">Status</th>
              {showBdm && <th scope="col">BDM</th>}
              <th scope="col">Dates</th><th scope="col">Route</th><th scope="col">Estimated</th><th scope="col">Actual</th><th scope="col">Mode</th>
            </tr>
          </thead>
          <tbody>
            {page.items.map((t) => (
              <tr key={t.id}>
                <td><Link href={detailHref(t.id)}>{t.code}</Link></td>
                <td>
                  <span className="badge state-badge">Approval: {APPROVAL_LABEL[t.approval_status]}</span>{" "}
                  <span className="badge state-badge">Travel: {TRAVEL_LABEL[t.travel_status]}</span>
                </td>
                {showBdm && <td>{t.bdm.full_name}</td>}
                <td>{formatCalendarDate(t.travel_date)}{t.return_date !== t.travel_date && <> – {formatCalendarDate(t.return_date)}</>}</td>
                <td>{t.from_place} → {t.to_place}</td>
                <td>{formatInr(t.estimated_cost)}</td>
                <td>{formatInr(t.actual_cost)}</td>
                <td>{MODE_LABEL[t.mode]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {page.total > page.limit && (
        <nav className="pager" aria-label={`${label} pages`}>
          <span className="muted" style={{ fontSize: 13 }}>Showing {page.offset + 1}–{end} of {page.total}</span>
          {page.offset > 0 && <Link className="btn secondary small" aria-label="Previous page" href={href(Math.max(0, page.offset - page.limit))}>Previous</Link>}
          {end < page.total && <Link className="btn secondary small" aria-label="Next page" href={href(end)}>Next</Link>}
        </nav>
      )}
    </>
  );
}
