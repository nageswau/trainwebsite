import Link from "next/link";

import CandidateJobApply from "@/components/CandidateJobApply";
import { dayText, employmentLabel, experienceText, type JobCard, type JobsPage, pageHref, VIEWS, workModeLabel } from "@/lib/candidateJobs";

// hrc-027 (DEC-SCOPE-398 J3-J6, J12): the three views as links (the address keeps the view, search and page, so refresh and back work),
// a search, the cards and the "not a guarantee" disclaimer (AC4). Shared by the candidate portal and the student portal.
function Card({ job }: { job: JobCard }) {
  const mode = workModeLabel(job.work_mode);
  // QA27-02: a remote job's location is often "Remote" too -- say it once
  const facts = [job.location, mode?.toLowerCase() === job.location.trim().toLowerCase() ? null : mode, employmentLabel(job.employment_type),
    experienceText(job.experience_min_months, job.experience_max_months)].filter(Boolean);
  return (
    <li className="panel" style={{ display: "grid", gap: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", alignItems: "flex-start" }}>
        <div>
          <h3 style={{ margin: 0 }}>{job.title}</h3>
          <p className="muted" style={{ margin: "4px 0 0" }}>{job.company}</p>
        </div>
        {job.match && <span className="badge badge-done">{job.match.score}% match</span>}
      </div>
      {facts.length > 0 && <p style={{ margin: 0 }}>{facts.join(" · ")}</p>}
      {job.required_skills.length > 0 && <p style={{ margin: 0 }}><strong>Required skills:</strong> {job.required_skills.join(", ")}</p>}
      {job.preferred_skills.length > 0 && <p style={{ margin: 0 }}><strong>Preferred skills:</strong> {job.preferred_skills.join(", ")}</p>}
      {job.closes_on && <p style={{ margin: 0 }}><strong>Apply by:</strong> {dayText(job.closes_on)}</p>}
      <div>
        <strong>Why this job</strong>
        {job.match ? (
          <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
            {job.match.explanation.map((line) => (
              <li key={line.key}>{line.label}: {line.text}</li>
            ))}
          </ul>
        ) : (
          <p style={{ margin: "4px 0 0" }}>{job.skills_text}</p>
        )}
      </div>
      <CandidateJobApply job={job} />
    </li>
  );
}

export default function CandidateJobsBoard({ data, base, profileHref }: { data: JobsPage; base: string; profileHref: string }) {
  const q = data.q ?? "";
  const view = VIEWS.find((v) => v.key === data.view) ?? VIEWS[0];
  const noSkills = data.reason === "no_skills" && data.view !== "all";
  const end = data.offset + data.items.length;
  return (
    <div style={{ display: "grid", gap: 16 }}>
      <form method="get" action={base} role="search" style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "flex-end" }}>
        <input type="hidden" name="view" value={data.view} />
        <label style={{ display: "grid", gap: 4, flex: "1 1 260px" }}>
          <span>Search jobs</span>
          <input name="q" type="search" defaultValue={q} maxLength={100} placeholder="Title, company, location or skill" />
        </label>
        <button className="btn secondary" type="submit">Search</button>
        {q && <Link className="btn secondary" href={pageHref(base, data.view, "")}>Clear</Link>}
      </form>
      <nav aria-label="Job views" className="report-tablist wrap">
        {VIEWS.map((v) => (
          <Link key={v.key} className="s360-tab" href={pageHref(base, v.key, q)} aria-current={v.key === data.view ? "page" : undefined}>
            {v.label} ({data.counts[v.key]})
          </Link>
        ))}
      </nav>
      <p className="muted" style={{ margin: 0 }}>{data.disclaimer}</p>
      {noSkills && (
        <div className="panel" role="status">
          <p style={{ margin: 0 }}>
            Recommendations appear once your skills are on your profile. <Link href={profileHref}>Go to your profile</Link>, or ask your
            recruiter to add them. Meanwhile, every job you can apply to is under <Link href={pageHref(base, "all", q)}>All open jobs</Link>.
          </p>
        </div>
      )}
      {data.items.length === 0 && data.total > 0 ? (
        <p className="empty">
          This page is past the end of the list. <Link href={pageHref(base, data.view, q)}>Go to the first page</Link>
        </p>
      ) : data.items.length === 0 ? (
        !noSkills && <p className="empty">{q ? `No jobs match “${q}” in this view.` : view.empty}</p>
      ) : (
        <>
          <p className="muted" style={{ margin: 0 }} aria-live="polite">Showing {data.offset + 1}–{end} of {data.total}</p>
          <ul className="panel-list" style={{ listStyle: "none", padding: 0, margin: 0 }} aria-label={view.label}>
            {data.items.map((job) => <Card key={job.id} job={job} />)}
          </ul>
        </>
      )}
      {(data.offset > 0 || end < data.total) && (
        <nav aria-label="Pages" style={{ display: "flex", gap: 8 }}>
          {data.offset > 0 && <Link className="btn secondary" href={pageHref(base, data.view, q, Math.max(0, data.offset - data.limit))}>Previous</Link>}
          {end < data.total && <Link className="btn secondary" href={pageHref(base, data.view, q, end)}>Next</Link>}
        </nav>
      )}
    </div>
  );
}
