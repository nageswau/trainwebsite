import Link from "next/link";

import RecruiterReassign from "@/components/RecruiterReassign";
import type { Page } from "@/lib/apiErrors";
import type { RecruiterTeamMember } from "@/lib/recruiter";
import { statusLabel } from "@/lib/telecaller";

const TEAM_PATH = "/recruiter/manager/team";

// rec-001 (AC4): a placement manager's direct reports. Server-rendered; paging is a link (?offset=), like TelecallerTeamTable.
// rec-037 (RC15): each row shows the recruiter's companies, requirements and open follow-ups, and Reassign (a client island) moves them.
// `data-label` names each cell, so below 640 px (globals.css .telecaller-list) a row becomes a card of labelled lines.
export default function RecruiterTeamTable({ page }: { page: Page<RecruiterTeamMember> }) {
  const end = page.offset + page.items.length;
  return (
    <div className="telecaller-list">
      <div className="table-wrap" role="region" aria-label="Team" tabIndex={0}>
        <table>
          <caption className="visually-hidden">Recruiters who report to you</caption>
          <thead>
            <tr>
              <th scope="col">Name</th><th scope="col">Employee ID</th><th scope="col">Email</th><th scope="col">Mobile</th><th scope="col">Status</th>
              <th scope="col">Companies</th><th scope="col">Requirements</th><th scope="col">Open follow-ups</th><th scope="col">Actions</th>
            </tr>
          </thead>
          <tbody>
            {page.items.map((r) => (
              <tr key={r.id}>
                <td data-label="Name">{r.full_name}</td>
                <td data-label="Employee ID">{r.employee_id ?? "—"}</td>
                <td data-label="Email" style={{ overflowWrap: "anywhere" }}>{r.email}</td>
                <td data-label="Mobile">{r.phone ?? "—"}</td>
                <td data-label="Status"><span className="badge">{statusLabel(r.active)}</span></td>
                <td data-label="Companies">{r.work.companies}</td>
                <td data-label="Requirements">{r.work.requirements}</td>
                <td data-label="Open follow-ups">{r.work.follow_ups}</td>
                <td data-label="Actions"><RecruiterReassign row={r} /></td>
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
    </div>
  );
}
