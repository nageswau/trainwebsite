import type { ReactNode } from "react";

import SectionUnavailable from "@/components/SectionUnavailable";
import type { CrossSchoolSummary, SchoolUtilizationPage, TrackedValue } from "@/lib/types";

// ENH-016 (School CRM.md §34 + §27 school-wise, D1): aggregates only -- no student-level data reaches this page (spec §12).
const OUTCOME_LABELS: Record<string, string> = { applications: "Applications", offers: "Offers", scholarships: "Scholarships", visas: "Visas", admissions: "Admissions", internships: "Internships" };
const pct = (v: number | null) => (v === null ? "—" : `${v}%`);
const num = (v: number) => v.toLocaleString("en-IN");

function Group({ title, items }: { title: string; items: [string, ReactNode][] }) {
  return (
    <section aria-label={title} className="kpi-group">
      <h3>{title}</h3>
      <dl className="kpi-grid">
        {items.map(([label, value]) => (
          <div className="kpi-tile" key={label}>
            <dt>{label}</dt>
            <dd className="kpi-value">{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function tracked(t: TrackedValue): ReactNode {
  if (t.tracked && t.value !== null) return num(t.value);
  return (
    <>
      <span className="badge">Not tracked yet</span>
      {t.note && <span className="kpi-note muted">{t.note}</span>}
    </>
  );
}

type Props = { summary: CrossSchoolSummary | null; page: SchoolUtilizationPage | null; basePath: string; q?: string };

export default function CrossSchoolAnalytics({ summary, page, basePath, q = "" }: Props) {
  const href = (offset: number) => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (offset > 0) params.set("offset", String(offset));
    const query = params.toString();
    return query ? `${basePath}?${query}` : basePath;
  };
  const pastEnd = !!page && page.items.length === 0 && page.total > 0;
  const lastOffset = page ? Math.max(0, Math.floor((page.total - 1) / page.limit) * page.limit) : 0;
  // Past the end, Previous goes to the real last page, not to another empty one (QA-016-07).
  const prev = page && page.offset > 0 ? (pastEnd ? lastOffset : Math.max(0, page.offset - page.limit)) : null;
  const next = page && page.offset + page.limit < page.total ? page.offset + page.limit : null;
  const empty = pastEnd ? "This page is past the end of the list." : q ? `No schools match “${q}”.` : "No partner schools yet.";
  return (
    <>
      {summary ? (
        <div className="card">
          <h2>All partner schools</h2>
          <Group title="Schools" items={[["Total", num(summary.schools.total)], ["Active", num(summary.schools.active)], ["New (90 days)", num(summary.schools.new)], ["Renewal due (60 days)", num(summary.schools.renewal_due)]]} />
          <Group
            title="Students"
            items={[["Total", num(summary.students.total)], ["Career guidance", num(summary.students.career_guidance)], ["Psychometric", num(summary.students.psychometric)], ["Counselling", num(summary.students.counselling)], ["Global education", num(summary.students.global_education)]]}
          />
          <Group title="Services" items={[["Delivered", num(summary.services.delivered)], ["Pending", num(summary.services.pending)], ["Not tracked", num(summary.services.not_tracked)], ["Utilization", pct(summary.services.utilization_pct)]]} />
          <Group title="Outcomes" items={Object.entries(summary.outcomes).map(([key, value]) => [OUTCOME_LABELS[key] ?? key, tracked(value)])} />
        </div>
      ) : (
        <SectionUnavailable title="All partner schools" />
      )}
      {page ? (
        <div className="card">
          <h2>Service utilization by school</h2>
          {/* QA-016-09: find one school among many; a plain GET form, so the search lives in the URL. */}
          <form method="get" action={basePath} className="analytics-form" role="search">
            <div className="field">
              <label htmlFor="school-search">Search schools</label>
              <input id="school-search" name="q" type="search" maxLength={200} defaultValue={q} />
            </div>
            <button className="btn secondary" type="submit">Search</button>
          </form>
          {page.items.length === 0 ? (
            <p className="muted">{empty}</p>
          ) : (
            <div className="table-scroll">
              <table className="table">
                <caption className="visually-hidden">Service utilization by school</caption>
                <thead>
                  <tr>
                    {["School", "Tier", "Students", "Participating", "Delivered", "Pending", "Not tracked", "Utilization", "Upcoming activities", "Flags"].map((h) => <th scope="col" key={h}>{h}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {page.items.map((r) => (
                    <tr key={r.school_id}>
                      <th scope="row">{r.name}</th>
                      <td>{r.tier ? r.tier.charAt(0).toUpperCase() + r.tier.slice(1) : "No tier"}</td>
                      <td>{num(r.students)}</td>
                      <td>{num(r.student_participation)}</td>
                      <td>{r.delivered}</td>
                      <td>{r.pending}</td>
                      <td>{r.not_tracked}</td>
                      <td>{pct(r.utilization_pct)}</td>
                      <td>{r.pending_activities}</td>
                      <td>
                        {r.is_new && <span className="badge">New</span>}
                        {r.renewal_due && <span className="badge">Renewal due</span>}
                        {!r.is_active && <span className="badge">No active tier</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {(prev !== null || next !== null) && (
            <nav className="pager" aria-label="School pages">
              {prev !== null && <a href={href(prev)} aria-label="Previous page">← Previous</a>}
              {page.items.length > 0 && <span className="muted">{`${page.offset + 1}–${page.offset + page.items.length} of ${page.total}`}</span>}
              {next !== null && <a href={href(next)} aria-label="Next page">Next →</a>}
            </nav>
          )}
        </div>
      ) : (
        <SectionUnavailable title="Service utilization by school" />
      )}
    </>
  );
}
