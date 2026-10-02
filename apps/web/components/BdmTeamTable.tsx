import Link from "next/link";

import type { Page } from "@/lib/apiErrors";
import { BDM_TYPE_LABEL, statusLabel, type BdmTeamRow } from "@/lib/bdm";

const TEAM_PATH = "/bdm/manager/team";

// bdm-001 (AC06): a manager's BDMs. Server-rendered; paging is a link (?offset=) so a page can be shared and needs no client JS.
export default function BdmTeamTable({ page }: { page: Page<BdmTeamRow> }) {
  const end = page.offset + page.items.length;
  return (
    <>
      <div className="table-wrap" role="region" aria-label="Team" tabIndex={0}>
        <table>
          {/* QA-16: the page heading already says this; the caption stays for screen readers only. */}
          <caption className="sr-only">BDMs who report to you</caption>
          <thead>
            <tr><th scope="col">Name</th><th scope="col">Employee ID</th><th scope="col">Module</th><th scope="col">Territory</th><th scope="col">Mobile</th><th scope="col">Status</th></tr>
          </thead>
          <tbody>
            {page.items.map((r) => (
              <tr key={r.id}>
                <td>{r.full_name}</td>
                <td>{r.employee_id}</td>
                <td>{BDM_TYPE_LABEL[r.bdm_type]}</td>
                <td>{r.territory ?? "—"}</td>
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
