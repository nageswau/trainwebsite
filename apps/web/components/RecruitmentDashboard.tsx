import Link from "next/link";

import { SpreadsheetButtons } from "@/components/ExportButtons";
import { formatCalendarDate, formatDateTimeIn, SCHOOL_TIME_ZONE } from "@/lib/formatDate";
import { formatCount } from "@/lib/managementCounseling";
import { BOARD_TABS, DASHBOARDS_PATH, exportUrl, pageHref, PAGE_SIZE, type Board, type BoardKey, type DashboardQuery, type Drill, type DrillColumn, type DrillRow, type Figure, type Option } from "@/lib/recruitmentDashboards";

type Filter = { name: "owner" | "employer" | "job"; label: string; options: Option[] };

function Tile({ figure, href }: { figure: Figure; href: string }) {
  return (
    <div className="kpi-tile">
      <dt>{figure.label}</dt>
      <dd>
        <Link className="kpi-value" href={href} aria-label={`${figure.label}: ${figure.value}. Open the records`}>{formatCount(figure.value)}</Link>
        <span className="kpi-note muted">{figure.definition}</span>
      </dd>
    </div>
  );
}

// The bar is decoration sized against the first stage; the count is the text (ManagementFunnel's pipeline-* styles).
function Stages({ label, figures, href }: { label: string; figures: Figure[]; href: (figure: Figure) => string }) {
  const max = Math.max(0, ...figures.map((f) => f.value));
  return (
    <ol className="pipeline-funnel" aria-label={label}>
      {figures.map((f) => (
        <li key={f.key} className="pipeline-stage">
          <span className="pipeline-label">{f.label}</span>
          <Link className="pipeline-count" href={href(f)} aria-label={`${f.label}: ${f.value}. Open the records`}>{formatCount(f.value)}</Link>
          <span className="pipeline-track" aria-hidden="true"><span className="pipeline-fill" style={{ width: `${max > 0 ? Math.round((f.value / max) * 100) : 0}%` }} /></span>
          <span className="metric-note">{f.definition}</span>
        </li>
      ))}
    </ol>
  );
}

function cell(column: DrillColumn, row: DrillRow) {
  const value = row[column.key];
  if (value === null || value === undefined) return "—";
  if (column.type === "date") return formatCalendarDate(String(value));
  if (column.type === "datetime") return formatDateTimeIn(String(value), SCHOOL_TIME_ZONE, true);
  return String(value);
}

function Records({ board, drill, query }: { board: BoardKey; drill: Drill; query: DashboardQuery }) {
  const [first, ...rest] = drill.columns;
  const pageTo = (offset: number) => pageHref(board, { ...query, offset });
  const hasPrevious = drill.offset > 0;
  const hasNext = drill.offset + drill.items.length < drill.total;
  return (
    <section id="records" aria-labelledby="records-heading" style={{ marginTop: 24 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12, justifyContent: "space-between", alignItems: "baseline" }}>
        <h3 id="records-heading" style={{ margin: 0 }}>{drill.figure.label}: {formatCount(drill.total)} {drill.total === 1 ? "record" : "records"}</h3>
        <Link className="btn secondary small" href={pageHref(board, { ...query, drill: "", offset: 0 })}>Close records</Link>
      </div>
      <p className="muted">{drill.figure.definition}</p>
      {drill.items.length === 0 ? (
        <p className="empty">No records for this figure.</p>
      ) : (
        <div className="table-wrap">
          <table className="table compact stack">
            <caption className="visually-hidden">The records behind {drill.figure.label}</caption>
            <thead>
              <tr>{drill.columns.map((c) => <th key={c.key} scope="col">{c.label}</th>)}</tr>
            </thead>
            <tbody>
              {drill.items.map((row) => (
                <tr key={row.id}>
                  <th scope="row" data-label={first.label}>{row.href ? <Link href={row.href}>{cell(first, row)}</Link> : cell(first, row)}</th>
                  {rest.map((c) => <td key={c.key} data-label={c.label}>{cell(c, row)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {drill.total > drill.items.length && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", marginTop: 12 }}>
          <span className="muted">Showing {drill.offset + 1}–{drill.offset + drill.items.length} of {formatCount(drill.total)}</span>
          {hasPrevious && <Link className="btn secondary small" href={pageTo(Math.max(0, drill.offset - PAGE_SIZE))}>Previous page</Link>}
          {hasNext && <Link className="btn secondary small" href={pageTo(drill.offset + PAGE_SIZE)}>Next page</Link>}
        </div>
      )}
    </section>
  );
}

// hrc-033 (DEC-SCOPE-414): one board -- its filters, its figures (each a link to the records it counted) and, once one is chosen, those
// records. Server-rendered from a GET form, so refresh, back and shared links keep the state.
export default function RecruitmentDashboard({ board, data, drill, error, query }: { board: BoardKey; data: Board | null; drill: Drill | null; error: string; query: DashboardQuery }) {
  const clean = { ...query, drill: "", offset: 0 };
  const filters: Filter[] = [
    { name: "owner", label: data?.owner_label ?? "Owner", options: data?.options.owners ?? [] },
    { name: "employer", label: "Employer", options: data?.options.employers ?? [] },
    { name: "job", label: "Job", options: data?.options.jobs ?? [] },
  ];
  const figureHref = (figure: Figure) => pageHref(board, { ...clean, drill: figure.key });
  const nothing = data !== null && data.sections.every((section) => section.figures.every((figure) => figure.value === 0));
  return (
    <div className="action-card">
      <nav aria-label="Recruitment dashboards" style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 16 }}>
        {BOARD_TABS.map((tab) => (
          <Link key={tab.key} className={tab.key === board ? "btn small" : "btn secondary small"} aria-current={tab.key === board ? "page" : undefined} href={pageHref(tab.key, { ...clean, owner: "" })}>{tab.label}</Link>
        ))}
      </nav>
      {error && <p className="form-error" role="alert">{error}</p>}
      <form key={JSON.stringify(clean)} method="get" action={`${DASHBOARDS_PATH}/${board}`} aria-label="Filter this dashboard" className="analytics-form" autoComplete="off">
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="dash-from">From</label>
          <input id="dash-from" className="input" type="date" name="from" defaultValue={query.from || (data?.date_from ?? "")} />
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="dash-to">To</label>
          <input id="dash-to" className="input" type="date" name="to" defaultValue={query.to || (data?.date_to ?? "")} />
        </div>
        {filters.map((filter) => (
          <div key={filter.name} className="field" style={{ margin: 0, minWidth: 0, maxWidth: "100%" }}>
            <label htmlFor={`dash-${filter.name}`}>{filter.label}</label>
            <select id={`dash-${filter.name}`} className="input" name={filter.name} defaultValue={query[filter.name]} style={{ maxWidth: "100%" }}>
              <option value="">All</option>
              {filter.options.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
            </select>
          </div>
        ))}
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="dash-branch">Branch</label>
          <select id="dash-branch" className="input" disabled aria-describedby="dash-branch-note"><option>Not recorded</option></select>
        </div>
        <button className="btn secondary" type="submit">Apply</button>
        <Link className="btn secondary" href={`${DASHBOARDS_PATH}/${board}`}>Clear filters</Link>
      </form>
      <p id="dash-branch-note" className="muted">Branch is not recorded on jobs, candidates or recruiters yet, so it cannot be used as a filter.</p>
      {data && <p className="muted">{data.note}</p>}
      {data?.can_download && <SpreadsheetButtons csvUrl={exportUrl(board, clean)} filename={`recruitment-${board}.csv`} label={`Export ${data.label}`} />}
      {nothing && <p className="empty" role="status">Nothing to show for these filters. Try a wider period or fewer filters.</p>}
      {data?.sections.map((section) => (
        <section key={section.key} aria-label={section.label}>
          <h3>{section.label}</h3>
          {board === "funnel" ? (
            <Stages label={section.label} figures={section.figures} href={figureHref} />
          ) : (
            <dl className="kpi-grid dashboard-tiles">
              {section.figures.map((figure) => <Tile key={figure.key} figure={figure} href={figureHref(figure)} />)}
            </dl>
          )}
        </section>
      ))}
      {drill && <Records board={board} drill={drill} query={query} />}
    </div>
  );
}
