import Link from "next/link";

import { type Filters, type Performance, periodText, TYPE_LABEL, typePath, valueText } from "@/lib/bdmPerformance";
import { LINK_STYLE } from "@/lib/bdmOrganizations";

// bdm-024 (DEC-SCOPE-113 §6): the §5 management view -- KPIs x BDM types for the period. Every tracked number links to the BDMs of its
// type (P8); an untracked one says so and is not a link (AC3). The table scrolls inside its box on a phone (AC5).
const NOTE = { margin: "4px 0 0" } as const;

export default function BdmPerformanceTable({ data, filters }: { data: Performance; filters: Filters }) {
  const types = data.rows[0]?.cells.map((c) => c.type) ?? [];
  const noBdms = data.rows.find((r) => r.key === "P-01")?.cells.every((c) => c.value === 0) ?? false; // QA24-04: say why it is all 0
  return (
    <section className="card" aria-labelledby="performance-by-type">
      <h3 id="performance-by-type" style={{ margin: 0, fontSize: 18 }}>Performance by BDM type</h3>
      {noBdms && <p className="muted" style={NOTE}>No active BDMs in this team yet.</p>}
      <div className="table-scroll">
        <table className="table">
          <caption className="visually-hidden">{`BDM performance by type, ${periodText(data.from, data.to)}`}</caption>
          <thead>
            <tr>
              <th scope="col">KPI</th>
              {types.map((t) => <th scope="col" key={t}>{TYPE_LABEL[t]}</th>)}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row) => (
              <tr key={row.key}>
                <th scope="row">{row.label}</th>
                {row.cells.map((cell) => (
                  <td key={cell.type}>
                    {cell.tracked ? (
                      <Link href={typePath(cell.type, filters)} style={LINK_STYLE}
                        aria-label={`${TYPE_LABEL[cell.type]} ${row.label}: ${valueText(cell.value)}. View the BDMs`}>
                        {valueText(cell.value)}
                      </Link>
                    ) : (
                      <span className="badge">Not tracked</span>
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h4 style={{ margin: "16px 0 0", fontSize: 15 }}>How each figure is counted</h4>
      <ul className="muted" style={{ margin: "4px 0 0", paddingLeft: 18 }}>
        {data.rows.map((row) => {
          const same = row.cells.every((c) => c.definition === row.cells[0]?.definition);
          return (
            <li key={row.key} style={NOTE}>
              {same
                ? `${row.label}: ${row.cells[0]?.definition ?? ""}`
                : `${row.label} — ${row.cells.map((c) => `${TYPE_LABEL[c.type]}: ${c.definition}`).join(" ")}`}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
