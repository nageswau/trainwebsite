import Link from "next/link";

import { FIGURE_COLUMNS, type Figures, valueText } from "@/lib/bdmPerformance";
import { LINK_STYLE } from "@/lib/bdmOrganizations";

// bdm-024 (DEC-SCOPE-111 §6): the drill-down tables -- the BDMs of a type (L2) and one BDM's organizations (L3). Each row's name and
// numbers link to its next level; the Total row is the level above's figure (P8). A figure that does not apply (an organization's
// trips) is a dash; an untracked one (Agent / School revenue) says so. Neither is a link.
export type FigureRow = { key: string; name: string; href: string; note?: string; figures: Figures };

function cell(row: FigureRow | null, label: string, value: number | string | null | undefined) {
  if (value === undefined) return <span aria-label="Does not apply">—</span>;
  if (value === null) return <span className="badge">Not tracked</span>;
  if (!row) return valueText(value);
  return <Link href={row.href} style={LINK_STYLE} aria-label={`${row.name} ${label}: ${valueText(value)}`}>{valueText(value)}</Link>;
}

/** `trips: null` on an organization row means "does not apply"; elsewhere null means "not tracked". */
const shown = (figures: Figures, key: keyof Figures) => (key === "trips" && figures.trips === null ? undefined : figures[key]);

export default function BdmPerformanceFigures({ caption, first, rows, total, empty }: {
  caption: string; first: string; rows: FigureRow[]; total: Figures; empty: string;
}) {
  if (rows.length === 0) return <p className="muted">{empty}</p>;
  return (
    <div className="table-scroll">
      <table className="table">
        <caption className="visually-hidden">{caption}</caption>
        <thead>
          <tr>
            <th scope="col">{first}</th>
            {FIGURE_COLUMNS.map(([key, label]) => <th scope="col" key={key}>{label}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key}>
              <th scope="row">
                <Link href={row.href} style={LINK_STYLE}>{row.name}</Link>
                {row.note && <> <span className="badge">{row.note}</span></>}
              </th>
              {FIGURE_COLUMNS.map(([key, label]) => <td key={key}>{cell(row, label, shown(row.figures, key))}</td>)}
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <th scope="row">Total</th>
            {FIGURE_COLUMNS.map(([key, label]) => <td key={key}><strong>{cell(null, label, shown(total, key))}</strong></td>)}
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
