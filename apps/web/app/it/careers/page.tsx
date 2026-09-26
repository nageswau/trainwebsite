import PublicShell from "@/components/PublicShell";
import PageHero from "@/components/PageHero";
import CareerApply from "@/components/CareerApply";
import CareerTracker from "@/components/CareerTracker";
import CollectionExplorer from "@/components/CollectionExplorer";
import {publicApi} from "@/lib/api";
import {formatCalendarDate} from "@/lib/formatDate";

export default async function Careers() {
  let jobs: any[] = [];
  try { jobs = await publicApi<any[]>("/api/v1/public/jobs"); } catch {}
  const items = jobs.map(job => ({
    id: String(job.id), searchText: `${job.title} ${job.company} ${job.location} ${(job.skills || []).join(" ")}`,
    filters: {company: job.company, location: job.location}, sortValues: {title: job.title, company: job.company, closes: job.closes_on},
    content: <div className="card"><span className="badge">Open</span><h3 style={{marginTop: 12}}>{job.title}</h3><p><strong>{job.company}</strong> · {job.location}</p><p className="muted">Skills: {(job.skills || []).join(", ")}</p><p className="muted">Closes: {job.closes_on ? formatCalendarDate(job.closes_on) : "Open until filled"}</p><CareerApply jobId={job.id} jobTitle={job.title}/></div>,
  }));
  return <PublicShell division="it"><PageHero eyebrow="Career Portal" title="Current Openings" description="Browse active employer opportunities, apply online with a resume, and keep your tracking code to check application progress."/><section className="section compact"><div className="container grid two"><div><CollectionExplorer items={items} noun="jobs" searchPlaceholder="Search role, company, location, or skill…" filters={[{key: "company", label: "Company"}, {key: "location", label: "Location"}]} sorts={[{value: "title", key: "title", label: "Role A–Z"}, {value: "company", key: "company", label: "Company A–Z"}, {value: "closes", key: "closes", label: "Closing soon"}]} layoutClassName="grid" initialPageSize={6} empty={<div className="card"><h3>No current openings</h3><p className="muted">New jobs appear here when the placement or HR team publishes a requirement.</p></div>}/></div><aside className="card" style={{alignSelf: "start"}}><h2>Track an application</h2><p className="muted">Use the tracking code shown after your public application.</p><CareerTracker/><hr style={{border: 0, borderTop: "1px solid var(--line)", margin: "24px 0"}}/><p className="muted">Enrolled EduSphere students can also sign in to use their saved profile and see placement-specific applications.</p><a className="btn secondary small" href="/it/login">Student login</a></aside></div></section></PublicShell>;
}
