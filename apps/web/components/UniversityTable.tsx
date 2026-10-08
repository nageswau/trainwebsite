import Link from "next/link";

import type { Page } from "@/lib/apiErrors";
import { INSTITUTION_TYPES, label, pageHref, POTENTIALS, type Filters, universityPath, type UniversityRow, visibilityLabel } from "@/lib/universities";

// upc-003: the University Master list. Server-rendered; paging is a link that keeps the filters, so a page can be shared. Below 640 px
// each row is a card of labelled lines (globals.css .telecaller-list reads each cell's data-label).
export default function UniversityTable({ page, filters }: { page: Page<UniversityRow>; filters: Filters }) {
  const end = page.offset + page.items.length;
  return (
    <div className="telecaller-list">
      <div className="table-wrap" role="region" aria-label="Universities" tabIndex={0}>
        <table>
          <caption className="visually-hidden">Universities, {page.total} in total</caption>
          <thead>
            <tr>
              <th scope="col">Name</th><th scope="col">Code</th><th scope="col">Type</th><th scope="col">Country</th><th scope="col">City</th>
              <th scope="col">Priority</th><th scope="col">Potential</th><th scope="col">Primary manager</th><th scope="col">Status</th>
            </tr>
          </thead>
          <tbody>
            {page.items.map((u) => (
              <tr key={u.id}>
                <td data-label="Name"><Link href={universityPath(u.id)}>{u.name}</Link></td>
                <td data-label="Code">{u.university_code}</td>
                <td data-label="Type">{label(INSTITUTION_TYPES, u.institution_type)}</td>
                <td data-label="Country">{u.country.name}</td>
                <td data-label="City">{u.city || "—"}</td>
                <td data-label="Priority">{u.priority ?? "—"}</td>
                <td data-label="Potential">{label(POTENTIALS, u.partnership_potential)}</td>
                <td data-label="Primary manager">{u.primary_manager?.full_name ?? "Unassigned"}</td>
                <td data-label="Status"><span className="badge">{visibilityLabel(u)}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {page.total > page.limit && (
        <nav aria-label="University pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
          <span className="muted" style={{ fontSize: 13 }}>Showing {page.offset + 1}–{end} of {page.total}</span>
          {page.offset > 0 && <Link className="btn secondary small" aria-label="Previous page" href={pageHref(filters, Math.max(0, page.offset - page.limit))}>Previous</Link>}
          {end < page.total && <Link className="btn secondary small" aria-label="Next page" href={pageHref(filters, end)}>Next</Link>}
        </nav>
      )}
    </div>
  );
}
