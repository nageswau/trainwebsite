import Link from "next/link";

import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { COMPANIES_PATH, personName, PRIORITY_LABEL, type Priority } from "@/lib/recruiterCompanies";
import { type BoardView, LOST } from "@/lib/recruiterPipeline";

type Change = { stage?: string | null; offset?: number };
const SELECTED = { display: "block", borderColor: "var(--blue)", boxShadow: "0 0 0 1px var(--blue)" } as const;

// rec-005 (P7): a count tile per stage plus Lost, and one page of companies (the BdmPipelineBoard look). Server-rendered: every filter is
// in the address, and filter links are plain <a> (a full page load, bdm-004 QA4-01) so back and shared links just work.
export default function RecruiterPipelineBoard({ view, href, selected }: { view: BoardView; href: (change: Change) => string; selected: string | null }) {
  const tiles = [...view.stages, { key: LOST, label: "Lost", count: view.lost_count }];
  const heading = tiles.find((t) => t.key === selected)?.label ?? "All open companies";
  const last = view.offset + view.items.length;
  return (
    <>
      <nav aria-label="Pipeline stages">
        <ul className="metric-grid pipeline-tiles" style={{ listStyle: "none", padding: 0 }}>
          {tiles.map((t) => (
            <li key={t.key}>
              <a className="metric" href={href({ stage: t.key, offset: 0 })} aria-current={selected === t.key ? "true" : undefined} style={selected === t.key ? SELECTED : { display: "block" }}>
                <span>{t.label}</span>
                <strong>{t.count}</strong>
              </a>
            </li>
          ))}
        </ul>
      </nav>
      <section className="action-card wide" aria-label="Companies at this stage">
        <h3>{heading}</h3>
        {selected && (
          <p>
            <a href={href({ stage: null, offset: 0 })} style={LINK_STYLE}>Show all stages</a>
          </p>
        )}
        {view.items.length === 0 ? (
          <p className="empty" role="status">{view.offset > 0 ? "This page is past the end of the list." : "No companies at this stage."}</p>
        ) : (
          <div className="table-wrap" role="region" aria-label="Companies" tabIndex={0}>
            <table style={{ minWidth: 640 }}>
              <thead>
                <tr>
                  <th scope="col">Code</th>
                  <th scope="col">Company</th>
                  <th scope="col">City</th>
                  <th scope="col">Priority</th>
                  <th scope="col">Stage</th>
                  <th scope="col">Recruiter</th>
                </tr>
              </thead>
              <tbody>
                {view.items.map((r) => (
                  <tr key={r.id}>
                    <td style={{ whiteSpace: "nowrap" }}>{r.code}</td>
                    <td style={{ minWidth: 160, overflowWrap: "anywhere" }}>
                      <Link href={`${COMPANIES_PATH}/${r.id}`} style={LINK_STYLE}>{r.name}</Link>
                    </td>
                    <td style={{ overflowWrap: "anywhere" }}>{r.city ?? "—"}</td>
                    <td>{r.priority ? PRIORITY_LABEL[r.priority as Priority] : "—"}</td>
                    <td>
                      {r.stage_label}
                      {r.lost && <> <span className="badge">Lost</span></>}
                    </td>
                    <td>{personName(r.assigned_recruiter)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {view.total > view.limit && (
          <nav aria-label="Pipeline pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
            <span className="muted" style={{ fontSize: 13 }}>Showing {view.offset + 1}–{last} of {view.total}</span>
            {view.offset > 0 && <a className="btn secondary small" href={href({ offset: Math.max(0, view.offset - view.limit) })}>Previous</a>}
            {last < view.total && <a className="btn secondary small" href={href({ offset: view.offset + view.limit })}>Next</a>}
          </nav>
        )}
      </section>
    </>
  );
}
