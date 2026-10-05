import Link from "next/link";
import type { ReactNode } from "react";

import { PAGE_SIZE } from "@/lib/bdm";
import { LINK_STYLE, ORG_TYPE_LABEL } from "@/lib/bdmOrganizations";
import { LOST, type PipelineView } from "@/lib/bdmPipeline";

type Change = { stage?: string | null; offset?: number };
const SELECTED = { display: "block", borderColor: "var(--blue)", boxShadow: "0 0 0 1px var(--blue)" } as const;

// bdm-004 (spec §8.3): stage tiles (counts are links; live / volume steps say why they have no count) and the organizations at the
// chosen stage. Server-rendered: every filter is in the address, so the browser's back button and shared links just work.
export default function BdmPipelineBoard({ view, href, orgBasePath, selected, emptyText, emptyAction }: {
  view: PipelineView; href: (change: Change) => string; orgBasePath: string; selected: string | null; emptyText: string; emptyAction?: ReactNode;
}) {
  const tiles = [...view.stages, { key: LOST, label: "Lost", kind: "manual" as const, count: view.lost_count }];
  const heading = tiles.find((t) => t.key === selected)?.label ?? "All open organizations";
  const last = view.offset + view.items.length;
  return (
    <>
      <nav aria-label="Pipeline stages">
        <ul className="metric-grid" style={{ listStyle: "none", padding: 0 }}>
          {tiles.map((t) => (
            <li key={t.key}>
              {t.count === null ? (
                <div className="metric">
                  <span>{t.label}</span>
                  <strong style={{ fontSize: 15 }}>{t.kind === "live" ? "Awaiting handover" : "Not tracked"}</strong>
                </div>
              ) : (
                <Link className="metric" href={href({ stage: t.key, offset: 0 })} aria-current={selected === t.key ? "true" : undefined} style={selected === t.key ? SELECTED : { display: "block" }}>
                  <span>{t.label}</span>
                  <strong>{t.count}</strong>
                </Link>
              )}
            </li>
          ))}
        </ul>
      </nav>
      <section className="action-card wide" aria-label="Organizations at this stage">
        <h3>{heading}</h3>
        {selected && (
          <p>
            <Link href={href({ stage: null, offset: 0 })} style={LINK_STYLE}>Show all stages</Link>
          </p>
        )}
        {view.items.length === 0 ? (
          <>
            <p className="empty" role="status">{view.offset > 0 ? "This page is past the end of the list." : emptyText}</p>
            {emptyAction}
          </>
        ) : (
          <div className="table-wrap" role="region" aria-label="Organizations" tabIndex={0}>
            <table style={{ overflowWrap: "anywhere" }}>
              <thead>
                <tr>
                  <th scope="col">Code</th>
                  <th scope="col">Name</th>
                  <th scope="col">Type</th>
                  <th scope="col">City</th>
                  <th scope="col">Stage</th>
                  <th scope="col">Assigned BDM</th>
                </tr>
              </thead>
              <tbody>
                {view.items.map((r) => (
                  <tr key={r.id}>
                    <td style={{ whiteSpace: "nowrap" }}>{r.code}</td>
                    <td style={{ minWidth: 160 }}>
                      <Link href={`${orgBasePath}/${r.id}`} style={LINK_STYLE}>{r.name}</Link>
                    </td>
                    <td>{ORG_TYPE_LABEL[r.org_type]}</td>
                    <td>{r.city}</td>
                    <td>
                      {r.stage_label}
                      {r.lost && <> <span className="badge">Lost</span></>}
                    </td>
                    <td>{r.assigned_bdm.full_name}{!r.assigned_bdm.active && <span className="muted"> (inactive)</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {view.total > PAGE_SIZE && (
          <nav aria-label="Pipeline pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
            <span className="muted" style={{ fontSize: 13 }}>Showing {view.offset + 1}–{last} of {view.total}</span>
            {view.offset > 0 && <Link className="btn secondary small" href={href({ offset: Math.max(0, view.offset - PAGE_SIZE) })}>Previous</Link>}
            {last < view.total && <Link className="btn secondary small" href={href({ offset: view.offset + PAGE_SIZE })}>Next</Link>}
          </nav>
        )}
      </section>
    </>
  );
}
