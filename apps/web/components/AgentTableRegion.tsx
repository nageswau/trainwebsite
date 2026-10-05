// AGN-018 table helpers, shared with AGN-019's client panel (moved out of AgentDashboardPanel, whose module imports server-only
// code). No hooks, so it renders in server and client components alike.

export const n = (value: number) => value.toLocaleString("en-IN");

// Browser QA18-06: the visible heading names its scroll region (aria-labelledby), so the title is not repeated in a hidden caption.
// QA18-04: `compact` drops the shared .table min-width, so a two-column table fits a phone instead of hiding its numbers.
export const headingId = (title: string) => `agent-dashboard-${title.toLowerCase().replaceAll(" ", "-")}`;

// `stack`: on phones each row becomes a block and every number shows its column label (data-label) -- the staff table has too many
// columns to fit 320 px (QA18-04).
export function TableRegion({ title, head, stack = false, children }: { title: string; head: string[]; stack?: boolean; children: React.ReactNode }) {
  return (
    <div className="table-scroll" tabIndex={0} role="region" aria-labelledby={headingId(title)}>
      <table className={stack ? "table compact stack" : "table compact"}>
        <thead>
          <tr>
            {head.map((h) => (
              <th scope="col" key={h}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}
