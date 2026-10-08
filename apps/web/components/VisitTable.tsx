import Link from "next/link";

import type { Page } from "@/lib/apiErrors";
import { dateText, statusText, type VisitRow, visitPath } from "@/lib/visits";

// upc-010: a page of visits. Server-rendered; paging is a link built by the caller (it keeps the page's filters). Below 640 px each row
// is a card of labelled lines (globals.css .telecaller-list reads each cell's data-label).
export default function VisitTable({ page, label, pageHref, showUniversity = true }: {
  page: Page<VisitRow>; label: string; pageHref?: (offset: number) => string; showUniversity?: boolean;
}) {
  const end = page.offset + page.items.length;
  return (
    <div className="telecaller-list">
      <div className="table-wrap" role="region" aria-label={label} tabIndex={0}>
        <table>
          <caption className="visually-hidden">{label}, {page.total} in total</caption>
          <thead>
            <tr>
              <th scope="col">Visit</th>{showUniversity && <th scope="col">University</th>}<th scope="col">Country</th><th scope="col">City</th>
              <th scope="col">Lead</th><th scope="col">Proposed</th><th scope="col">Confirmed</th><th scope="col">Status</th>
            </tr>
          </thead>
          <tbody>
            {page.items.map((v) => (
              <tr key={v.id}>
                <td data-label="Visit"><Link href={visitPath(v.id)}>{v.code}</Link></td>
                {showUniversity && <td data-label="University">{v.university.name}</td>}
                <td data-label="Country">{v.university.country.name}</td>
                <td data-label="City">{v.city}</td>
                <td data-label="Lead">{v.lead.full_name}{v.lead.active ? "" : " (inactive)"}</td>
                <td data-label="Proposed">{dateText(v.proposed_date)}</td>
                <td data-label="Confirmed">{dateText(v.confirmed_date)}</td>
                <td data-label="Status"><span className="badge">{statusText(v)}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pageHref && page.total > page.limit && (
        <nav aria-label="Visit pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
          <span className="muted" style={{ fontSize: 13 }}>Showing {page.offset + 1}–{end} of {page.total}</span>
          {page.offset > 0 && <Link className="btn secondary small" aria-label="Previous page" href={pageHref(Math.max(0, page.offset - page.limit))}>Previous</Link>}
          {end < page.total && <Link className="btn secondary small" aria-label="Next page" href={pageHref(end)}>Next</Link>}
        </nav>
      )}
    </div>
  );
}
