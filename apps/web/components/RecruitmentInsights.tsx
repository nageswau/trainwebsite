import Link from "next/link";
import type { ReactNode } from "react";

import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { formatDate, formatSchoolDateTime } from "@/lib/formatDate";
import { MANAGEMENT_ROLE_LABEL, managementNavFor, type ManagementMe } from "@/lib/management";
import type { NavItem } from "@/lib/navigation";
import { companyShell } from "@/lib/recruiterCompanies";
import {
  type DataQuality, DEFAULT_N, type Drill, drillHref, type DrillValue, type Figure, INSIGHTS_BASE, INSIGHTS_PAGES, type InsightsPageKey, PAGE_SIZE, type PortalAnalytics, skillHref, type SkillDemand, type SkillParams, type Vacancies,
} from "@/lib/recruitmentInsights";
import type { User } from "@/lib/types";

// hrc-034 (DEC-SCOPE-416 I6): the three report pages. Server-rendered from GET forms and links; the API computes every figure.
const INTRO: Record<InsightsPageKey, string> = {
  "skill-demand": "What open jobs ask for, what the candidate pool holds, and the vacancies short of candidates.",
  "portal-analytics": "How students and portal candidates move from seeing a job to applying.",
  "data-quality": "Records that need correcting. Open a figure to see what it counts.",
};

export async function insightsShell(user: User): Promise<{ nav: NavItem[]; roleLabel: string }> {
  if (user.role !== "partner") return companyShell(user.role);
  const me = await serverApi<ManagementMe>("/api/v1/management/me");
  return { nav: managementNavFor(me.tiers), roleLabel: MANAGEMENT_ROLE_LABEL[me.role] ?? me.role };
}

export function InsightsFrame({ current, nav, roleLabel, userName, children }: { current: InsightsPageKey; nav: NavItem[]; roleLabel: string; userName: string; children: ReactNode }) {
  const title = INSIGHTS_PAGES.find((p) => p.key === current)?.label;
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={userName}>
      <div className="portal-content recruitment-insights">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Recruitment insights</div>
            <h2>{title}</h2>
            <p className="muted">{INTRO[current]}</p>
          </div>
        </div>
        <nav aria-label="Recruitment insights" className="report-tablist wrap" style={{ marginBottom: 16 }}>
          {INSIGHTS_PAGES.map((p) => (
            <Link key={p.key} className="s360-tab" href={`${INSIGHTS_BASE}/${p.key}`} aria-current={p.key === current ? "page" : undefined}>{p.label}</Link>
          ))}
        </nav>
        {children}
      </div>
    </PortalShell>
  );
}

function Tiles({ figures, title, link }: { figures: Figure[]; title: string; link?: (f: Figure) => ReactNode }) {
  return (
    <dl className="kpi-grid" aria-label={title}>
      {figures.map((f) => (
        <div className="kpi-tile" key={f.key}>
          <dt>{f.label}</dt>
          <dd className="kpi-value">{f.value}</dd>
          <dd className="kpi-note muted">{f.definition}</dd>
          {link && <dd>{link(f)}</dd>}
        </div>
      ))}
    </dl>
  );
}

function Pager({ label, offset, shown, total, href }: { label: string; offset: number; shown: number; total: number; href: (offset: number) => string }) {
  if (total <= shown && offset === 0) return null;
  return (
    <nav aria-label={label} style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginTop: 12 }}>
      {shown > 0 && <span className="muted">Showing {offset + 1}–{offset + shown} of {total}.</span>}
      {offset > 0 && <Link className="btn small secondary" href={href(Math.max(0, offset - PAGE_SIZE))}>Previous</Link>}
      {offset + shown < total && <Link className="btn small secondary" href={href(offset + shown)}>Next</Link>}
    </nav>
  );
}

// --- Skill demand -----------------------------------------------------------------------------------------------------------------------
export function SkillDemandView({ data, vacancies, params }: { data: SkillDemand; vacancies: Vacancies; params: SkillParams }) {
  const unchecked = vacancies.open_jobs - vacancies.checked;
  return (
    <div style={{ display: "grid", gap: 16 }}>
      <Tiles figures={data.figures} title="Skill demand figures" />
      <section className="panel" aria-labelledby="skills-heading">
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
          <h3 id="skills-heading" style={{ margin: 0 }}>Skills</h3>
          <nav aria-label="Sort skills" className="report-tablist wrap">
            <Link className="s360-tab" href={skillHref(params, { sort: "demand", offset: 0 })} aria-current={data.sort === "demand" ? "page" : undefined}>Most requested</Link>
            <Link className="s360-tab" href={skillHref(params, { sort: "supply", offset: 0 })} aria-current={data.sort === "supply" ? "page" : undefined}>Largest supply</Link>
          </nav>
        </div>
        {data.items.length === 0 ? (
          <p className="empty">{data.total > 0 ? <>This page is past the end of the list. <Link href={skillHref(params, { offset: 0 })}>Go to the first page</Link></> : "No open job lists a Skills Master skill and no candidate holds one yet."}</p>
        ) : (
          <table className="table compact stack">
            <caption className="visually-hidden">Demand and supply by skill</caption>
            <thead><tr><th scope="col">Skill</th><th scope="col">Category</th><th scope="col">Open jobs</th><th scope="col">Required by</th><th scope="col">Preferred by</th><th scope="col">Candidates</th></tr></thead>
            <tbody>
              {data.items.map((s) => (
                <tr key={s.skill_id}>
                  <th scope="row" data-label="Skill">{s.name}</th>
                  <td data-label="Category">{s.category}</td>
                  <td data-label="Open jobs">{s.open_jobs}</td>
                  <td data-label="Required by">{s.required_jobs}</td>
                  <td data-label="Preferred by">{s.preferred_jobs}</td>
                  <td data-label="Candidates">{s.supply}{s.zero_supply && <> <span className="badge zero-supply">No supply</span></>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <Pager label="Skill pages" offset={data.offset} shown={data.items.length} total={data.total} href={(offset) => skillHref(params, { offset })} />
      </section>
      <section className="panel" aria-labelledby="vacancies-heading">
        <h3 id="vacancies-heading" style={{ marginTop: 0 }}>Vacancies short of candidates</h3>
        <p className="muted">Open jobs with fewer than {vacancies.n} {vacancies.n === 1 ? "candidate" : "candidates"} through their hard filters; the same count as the requirement&apos;s Matching page.</p>
        <form className="form filter-bar" action={`${INSIGHTS_BASE}/skill-demand`} method="get" aria-label="Choose the candidate threshold" style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "flex-end" }}>
          {params.sort === "supply" && <input type="hidden" name="sort" value="supply" />}
          <div className="field">
            <label htmlFor="vacancy-n">Fewer than</label>
            <input id="vacancy-n" name="n" type="number" min={1} max={100} defaultValue={vacancies.n ?? DEFAULT_N} />
          </div>
          <button className="btn small secondary" type="submit">Apply</button>
        </form>
        {unchecked > 0 && <p className="form-message" role="status">Only the newest {vacancies.checked} of {vacancies.open_jobs} open jobs were checked.</p>}
        {vacancies.items.length === 0 ? (
          <p className="empty">{vacancies.total > 0 ? "This page is past the end of the list." : "Every open job checked has enough candidates."}</p>
        ) : (
          <table className="table compact stack">
            <caption className="visually-hidden">Open jobs short of candidates</caption>
            <thead><tr><th scope="col">Requirement</th><th scope="col">Title</th><th scope="col">Company</th><th scope="col">Candidates</th></tr></thead>
            <tbody>
              {vacancies.items.map((v) => (
                <tr key={v.id}>
                  <td data-label="Requirement">{v.code}</td>
                  <td data-label="Title">{v.title}</td>
                  <td data-label="Company">{v.company}</td>
                  <td data-label="Candidates">{v.matches}{v.reason === "no_skills" && <span className="muted"> (no Skills Master skill listed)</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <Pager label="Vacancy pages" offset={vacancies.offset} shown={vacancies.items.length} total={vacancies.total} href={(vacancyOffset) => skillHref(params, { vacancyOffset })} />
      </section>
    </div>
  );
}

// --- Portal analytics -------------------------------------------------------------------------------------------------------------------
export function PeriodForm({ from, to }: { from: string; to: string }) {
  return (
    <form className="form filter-bar" action={`${INSIGHTS_BASE}/portal-analytics`} method="get" aria-label="Choose the period" style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "flex-end", marginBottom: 16 }}>
      <div className="field"><label htmlFor="period-from">From</label><input id="period-from" name="from" type="date" defaultValue={from} /></div>
      <div className="field"><label htmlFor="period-to">To</label><input id="period-to" name="to" type="date" defaultValue={to} /></div>
      <button className="btn small secondary" type="submit">Apply</button>
      <Link className="btn small secondary" href={`${INSIGHTS_BASE}/portal-analytics`}>This month</Link>
    </form>
  );
}

export function PortalAnalyticsView({ data }: { data: PortalAnalytics }) {
  const quiet = data.funnel.every((s) => s.events === 0);
  return (
    <div style={{ display: "grid", gap: 16 }}>
      <section className="panel" aria-labelledby="registrations-heading">
        <h3 id="registrations-heading" style={{ marginTop: 0 }}>Registrations</h3>
        <dl className="kpi-grid">
          <div className="kpi-tile"><dt>Registered</dt><dd className="kpi-value">{data.registrations.total}</dd><dd className="kpi-note muted">Portal candidate accounts created in the period.</dd></div>
          <div className="kpi-tile"><dt>Email verified</dt><dd className="kpi-value">{data.registrations.verified}</dd><dd className="kpi-note muted">Of those, the accounts with a verified email.</dd></div>
        </dl>
      </section>
      <section className="panel" aria-labelledby="funnel-heading">
        <h3 id="funnel-heading" style={{ marginTop: 0 }}>Jobs and applications</h3>
        <p className="muted">Students and portal candidates, {formatDate(data.from)} to {formatDate(data.to)}. A person counts once per job, step and day.{data.first_recorded ? ` Recorded since ${formatDate(data.first_recorded)}.` : ""}</p>
        {quiet ? <p className="empty">No job activity in this period.</p> : (
          <table className="table compact stack">
            <caption className="visually-hidden">Steps from viewing a job to applying</caption>
            <thead><tr><th scope="col">Step</th><th scope="col">People</th><th scope="col">Dropped off</th><th scope="col">Events</th></tr></thead>
            <tbody>
              {data.funnel.map((s) => (
                <tr key={s.key}>
                  <th scope="row" data-label="Step">{s.label}</th>
                  <td data-label="People">{s.people}</td>
                  <td data-label="Dropped off">{s.dropped ?? "—"}</td>
                  <td data-label="Events">{s.events}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      <section className="panel" aria-labelledby="completion-heading">
        <h3 id="completion-heading" style={{ marginTop: 0 }}>Profile completion</h3>
        <p className="muted">Active portal candidates by profile completeness, right now (not limited to the period).</p>
        <table className="table compact stack">
          <caption className="visually-hidden">Portal candidates by profile completeness</caption>
          <thead><tr><th scope="col">Complete</th><th scope="col">Candidates</th></tr></thead>
          <tbody>{data.completion.map((b) => <tr key={b.label}><th scope="row" data-label="Complete">{b.label}</th><td data-label="Candidates">{b.count}</td></tr>)}</tbody>
        </table>
      </section>
    </div>
  );
}

// --- Data quality -----------------------------------------------------------------------------------------------------------------------
const DATE_COLUMNS = new Set(["created_at", "failed_at"]);

function cell(key: string, value: DrillValue): string {
  if (value === null) return "—";
  if (Array.isArray(value)) return value.join(", ");
  return DATE_COLUMNS.has(key) ? formatSchoolDateTime(String(value)) : String(value);
}

export function DataQualityView({ data, drill }: { data: DataQuality; drill: Drill | null }) {
  return (
    <div style={{ display: "grid", gap: 16 }}>
      <Tiles figures={data.figures} title="Data quality figures" link={(f) => (
        <span style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <Link className="kpi-link" href={drillHref(f.key)} aria-label={`Show what ${f.label} counts`}>Show records</Link>
          {f.href && <Link className="kpi-link" href={f.href} aria-label={`Fix ${f.label}`}>Fix these</Link>}
        </span>
      )} />
      {drill && (
        <section className="panel" aria-labelledby="drill-heading">
          <h3 id="drill-heading" style={{ marginTop: 0 }}>{drill.figure.label} ({drill.total})</h3>
          <p className="muted">{drill.figure.definition}</p>
          {drill.items.length === 0 ? (
            <p className="empty">{drill.total > 0 ? <>This page is past the end of the list. <Link href={drillHref(drill.figure.key)}>Go to the first page</Link></> : "Nothing to correct here."}</p>
          ) : (
            <table className="table compact stack">
              <caption className="visually-hidden">The records {drill.figure.label} counts</caption>
              <thead><tr>{drill.columns.map((c) => <th scope="col" key={c.key}>{c.label}</th>)}</tr></thead>
              <tbody>
                {drill.items.map((row, i) => (
                  <tr key={i}>{drill.columns.map((c) => <td key={c.key} data-label={c.label}>{cell(c.key, row[c.key] ?? null)}</td>)}</tr>
                ))}
              </tbody>
            </table>
          )}
          <Pager label="Record pages" offset={drill.offset} shown={drill.items.length} total={drill.total} href={(offset) => drillHref(drill.figure.key, offset)} />
        </section>
      )}
    </div>
  );
}
