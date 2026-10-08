import Link from "next/link";

import type { Page } from "@/lib/apiErrors";
import { TEAM_PATH, type PartnershipTeamRow } from "@/lib/partnership";
import { statusLabel } from "@/lib/telecaller";

// upc-001 (AC4): a head's direct reports. Server-rendered; paging is a link (?offset=) so a page can be shared and needs no client JS.
export default function PartnershipTeamTable({ page }: { page: Page<PartnershipTeamRow> }) {
  const end = page.offset + page.items.length;
  return (
    <>
      <div className="table-wrap" role="region" aria-label="Team" tabIndex={0}>
        <table>
          <caption className="visually-hidden">Partnership managers who report to you</caption>
          <thead>
            <tr><th scope="col">Name</th><th scope="col">Employee ID</th><th scope="col">Email</th><th scope="col">Mobile</th><th scope="col">Status</th></tr>
          </thead>
          <tbody>
            {page.items.map((r) => (
              <tr key={r.id}>
                <td>{r.full_name}</td>
                <td>{r.employee_id}</td>
                <td style={{ overflowWrap: "anywhere" }}>{r.email}</td>
                <td>{r.phone ?? "—"}</td>
                <td><span className="badge">{statusLabel(r.active)}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {page.total > page.limit && (
        <nav aria-label="Team pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
          <span className="muted" style={{ fontSize: 13 }}>Showing {page.offset + 1}–{end} of {page.total}</span>
          {page.offset > 0 && <Link className="btn secondary small" aria-label="Previous page" href={`${TEAM_PATH}?offset=${Math.max(0, page.offset - page.limit)}`}>Previous</Link>}
          {end < page.total && <Link className="btn secondary small" aria-label="Next page" href={`${TEAM_PATH}?offset=${end}`}>Next</Link>}
        </nav>
      )}
    </>
  );
}
