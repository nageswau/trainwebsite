import Link from "next/link";

import type { Page } from "@/lib/apiErrors";
import { PAGE_SIZE } from "@/lib/bdm";
import { MOU_STATUSES, type MouRow, type MouStatus, statusLabel } from "@/lib/bdmMous";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { formatCalendarDate } from "@/lib/formatDate";

// QA5-04: one row that scrolls sideways when it doesn't fit (ten wrapped buttons took ~5 rows on a phone); the links stay focusable.
const FILTERS = { display: "flex", gap: 8, flexWrap: "nowrap", overflowX: "auto", whiteSpace: "nowrap", padding: "0 0 6px", margin: "0 0 10px" } as const;
const day = (value: string | null) => (value ? formatCalendarDate(value) : "—");

// bdm-005 (spec §8): the scoped MoU list. Filters and pages are plain <a> -- a full page load (bdm-004 QA4-01); the table is a labelled
// region that scrolls sideways on phones with whole-word columns (QA4-02). The status is the derived one, so Expired lists past-date MoUs.
export default function BdmMousPanel({ page, status, path, orgBasePath }: { page: Page<MouRow>; status: MouStatus | null; path: string; orgBasePath: string }) {
  const href = (s: MouStatus | null, offset = 0) => {
    const q = new URLSearchParams();
    if (s) q.set("status", s);
    if (offset > 0) q.set("offset", String(offset));
    const query = q.toString();
    return query ? `${path}?${query}` : path;
  };
  const last = Math.min(page.offset + PAGE_SIZE, page.total);
  const empty = page.offset > 0 ? "This page is past the end of the list." : status ? `No MoUs at ${statusLabel(status)}.` : "No MoUs yet.";
  return (
    <>
      <nav aria-label="Filter by status" style={FILTERS}>
        {[{ key: null, label: "All" }, ...MOU_STATUSES].map((s) => (
          <a key={s.label} className={status === s.key ? "btn small" : "btn secondary small"} href={href(s.key)} aria-current={status === s.key ? "true" : undefined}>
            {s.label}
          </a>
        ))}
      </nav>
      <section className="action-card wide" aria-label="MoU list">
        <h3>{status ? statusLabel(status) : "All"} MoUs</h3>
        {page.items.length === 0 ? (
          <p className="empty" role="status">{empty}</p>
        ) : (
          <div className="table-wrap" role="region" aria-label="MoUs" tabIndex={0}>
            <table style={{ minWidth: 720 }}>
              <thead>
                <tr>
                  <th scope="col">Organization</th>
                  <th scope="col">Code</th>
                  <th scope="col">Status</th>
                  <th scope="col">Signed on</th>
                  <th scope="col">Valid until</th>
                  <th scope="col">Reference</th>
                  <th scope="col">Document</th>
                  <th scope="col">Assigned BDM</th>
                </tr>
              </thead>
              <tbody>
                {page.items.map((r) => (
                  <tr key={r.id}>
                    <td style={{ minWidth: 160, overflowWrap: "anywhere" }}>
                      <Link href={`${orgBasePath}/${r.organization.id}`} style={LINK_STYLE}>{r.organization.name}</Link>
                    </td>
                    <td style={{ whiteSpace: "nowrap" }}>{r.organization.code}</td>
                    <td>{r.status_label}</td>
                    <td style={{ whiteSpace: "nowrap" }}>{day(r.signed_on)}</td>
                    <td style={{ whiteSpace: "nowrap" }}>{day(r.valid_until)}</td>
                    <td style={{ overflowWrap: "anywhere" }}>{r.reference ?? "—"}</td>
                    <td>{r.has_document ? "Yes" : "—"}</td>
                    <td>{r.assigned_bdm.full_name}{!r.assigned_bdm.active && <span className="muted"> (inactive)</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {page.total > PAGE_SIZE && (
          <nav aria-label="MoU pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
            <span className="muted" style={{ fontSize: 13 }}>Showing {page.offset + 1}–{last} of {page.total}</span>
            {page.offset > 0 && <a className="btn secondary small" href={href(status, Math.max(0, page.offset - PAGE_SIZE))}>Previous</a>}
            {last < page.total && <a className="btn secondary small" href={href(status, page.offset + PAGE_SIZE)}>Next</a>}
          </nav>
        )}
      </section>
    </>
  );
}
