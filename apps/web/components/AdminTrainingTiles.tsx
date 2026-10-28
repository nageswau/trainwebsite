import Link from "next/link";

import { serverApi } from "@/lib/api";
import { pageHref, type ReportColumn, type ReportRow } from "@/lib/reports";

export type TrainingTiles = {
  enrolments: number; active: number; completed: number; dropped: number; average_progress: number | null; at_risk: number;
  at_risk_threshold: number; fees_collected?: number; fees_pending?: number;
  courses: { columns: ReportColumn[]; items: ReportRow[]; total: number };
};

const rupees = (value: number) => `₹${Number(value).toLocaleString("en-IN")}`;
const show = (value: ReportRow[string]) => (value === null || value === undefined || value === "" ? "—" : String(value));

// nehn-011 (DEC-SCOPE-311): the admin dashboard's training tiles, each a link to the nehn-010 report whose total it shows (the API
// computes both from one query). `training` is absent for a caller without the training reports; the fee figures are absent without
// `field.financial.view`, so their tiles are simply not drawn.
export default function AdminTrainingTiles({ training, basePath }: { training: TrainingTiles | undefined; basePath: string }) {
  if (!training) return null;
  const href = (report: string, params: Record<string, string> = {}) => pageHref(basePath, report, params, 1);
  const tiles: { label: string; value: string; href: string; hint?: string }[] = [
    { label: "Enrolments", value: String(training.enrolments), href: href("courses") },
    { label: "Active", value: String(training.active), href: href("courses") },
    { label: "Completed", value: String(training.completed), href: href("completions") },
    { label: "Dropped", value: String(training.dropped), href: href("courses") },
    { label: "Average progress", value: training.average_progress === null ? "—" : `${training.average_progress}%`, href: href("student-courses") },
    {
      label: "At-risk students", value: String(training.at_risk), hint: `Attendance below ${training.at_risk_threshold}%`,
      href: href("attendance", { attendance_below: String(training.at_risk_threshold) }),
    },
  ];
  if (training.fees_collected !== undefined) tiles.push({ label: "Course fees collected", value: rupees(training.fees_collected), href: href("courses") });
  if (training.fees_pending !== undefined) tiles.push({ label: "Course fees pending", value: rupees(training.fees_pending), href: href("courses") });
  const { columns, items, total } = training.courses;
  const [first, ...rest] = columns;
  return (
    <section className="action-card training-tiles" aria-labelledby="training-tiles-heading">
      <h3 id="training-tiles-heading">Training overview</h3>
      <div className="metric-grid">
        {tiles.map((tile) => (
          <Link className="metric" key={tile.label} href={tile.href}>
            <span>{tile.label}</span>
            <strong>{tile.value}</strong>
            {tile.hint && <small className="muted">{tile.hint}</small>}
          </Link>
        ))}
      </div>
      {items.length === 0 ? (
        <p className="empty" role="status">No courses with batches yet.</p>
      ) : (
        <div className="table-wrap">
          <table className="table compact stack">
            <caption className="visually-hidden">Course-wise summary</caption>
            <thead><tr>{columns.map((c) => <th key={c.key} scope="col">{c.label}</th>)}</tr></thead>
            <tbody>
              {items.map((row, index) => (
                <tr key={`${row[first.key]}-${index}`}>
                  <th scope="row">{show(row[first.key])}</th>
                  {rest.map((c) => <td key={c.key} data-label={c.label}>{show(row[c.key])}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p><Link href={href("courses")}>View the course-wise report{total > items.length ? ` (all ${total} courses)` : ""}</Link></p>
    </section>
  );
}

/** The IT Admin dashboard's copy: reads the tiles itself (the portal payload carries the page), and a failed read drops only them. */
export async function AdminTrainingPanel({ basePath }: { basePath: string }) {
  const dashboard = await serverApi<{ training?: TrainingTiles }>("/api/v1/admin/dashboard").catch(() => null);
  return <AdminTrainingTiles training={dashboard?.training} basePath={basePath} />;
}
