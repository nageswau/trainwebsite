import Link from "next/link";

import { type Board, type BoardChange, LOST } from "@/lib/partnershipPipeline";
import { universityPath } from "@/lib/universities";

const SELECTED = { display: "block", borderColor: "var(--blue)", boxShadow: "0 0 0 1px var(--blue)" } as const;

// upc-007 (PS12, the bdm-004 BdmPipelineBoard pattern): the nine §4 Kanban columns and Lost as count tiles (each a link), then the
// universities in the chosen column (or every open one). Server-rendered; every filter is in the address. Filter links are plain <a>
// (a full page load, bdm-004 QA4-01); university rows go to another route and stay next/link.
export default function PartnershipPipelineBoard({ view, href, selected }: { view: Board; href: (change: BoardChange) => string; selected: string | null }) {
  const tiles = [...view.columns, { key: LOST, label: "Lost", count: view.lost_count }];
  const heading = tiles.find((t) => t.key === selected)?.label ?? "All open universities";
  const last = view.offset + view.items.length;
  return (
    <>
      <nav aria-label="Pipeline columns">
        <ul className="metric-grid pipeline-tiles" style={{ listStyle: "none", padding: 0 }}>
          {tiles.map((t) => (
            <li key={t.key}>
              <a className="metric" href={href({ column: t.key, offset: 0 })} aria-current={selected === t.key ? "true" : undefined} style={selected === t.key ? SELECTED : { display: "block" }}>
                <span>{t.label}</span>
                <strong>{t.count}</strong>
              </a>
            </li>
          ))}
        </ul>
      </nav>
      <section className="action-card wide" aria-labelledby="pipeline-list">
        <h3 id="pipeline-list">{heading}</h3>
        {selected && (
          <p>
            <a href={href({ column: null, offset: 0 })}>Show all columns</a>
          </p>
        )}
        {view.items.length === 0 ? (
          <p className="empty" role="status">
            {view.offset > 0 ? "This page is past the end of the list." : selected ? "No universities in this column." : "No open universities yet."}
          </p>
        ) : (
          <div className="telecaller-list">
            <div className="table-wrap" role="region" aria-label="Universities in the pipeline" tabIndex={0}>
              <table>
                <thead>
                  <tr>
                    <th scope="col">Name</th>
                    <th scope="col">Code</th>
                    <th scope="col">Country</th>
                    <th scope="col">Stage</th>
                    <th scope="col">Primary manager</th>
                  </tr>
                </thead>
                <tbody>
                  {view.items.map((r) => (
                    <tr key={r.id}>
                      <td data-label="Name" style={{ overflowWrap: "anywhere" }}>
                        <Link href={universityPath(r.id)}>{r.name}</Link>
                      </td>
                      <td data-label="Code" style={{ whiteSpace: "nowrap" }}>{r.university_code}</td>
                      <td data-label="Country">{[r.city, r.country_name].filter(Boolean).join(", ")}</td>
                      <td data-label="Stage">
                        {r.stage_label}
                        {r.lost && <> <span className="badge">Lost</span></>}
                      </td>
                      <td data-label="Primary manager">
                        {r.primary_manager ? r.primary_manager.full_name : "Unassigned"}
                        {r.primary_manager && !r.primary_manager.active && <span className="muted"> (inactive)</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
        {view.total > view.limit && (
          <nav aria-label="Pipeline pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
            {view.items.length > 0 && <span className="muted" style={{ fontSize: 13 }}>Showing {view.offset + 1}–{last} of {view.total}</span>}
            {view.offset > 0 && <a className="btn secondary small" href={href({ offset: Math.max(0, view.offset - view.limit) })}>Previous</a>}
            {last < view.total && view.items.length > 0 && <a className="btn secondary small" href={href({ offset: last })}>Next</a>}
          </nav>
        )}
      </section>
    </>
  );
}
