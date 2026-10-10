import type { ReactNode } from "react";

import { safeWebsite } from "@/lib/bdmOrganizations";
import LocalTime from "@/components/LocalTime";
import { dateText } from "@/lib/universityAgreements";
import { INSTITUTION_TYPES, label, OWNERSHIP_TYPES, rankingText } from "@/lib/universities";
import { kindLabel } from "@/lib/universityDocuments";
import { englishText, money, type UniversityView, viewDocumentFileUrl } from "@/lib/universityView";

// upc-030 (DEC-SCOPE-161 UV11): the University 360 view, one component for every portal. Data only (a server component): it renders
// exactly the sections the API's role slice carries -- a section the slice leaves out is absent from the payload and from the page.
function Facts({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl style={{ display: "grid", gridTemplateColumns: "minmax(120px, max-content) 1fr", gap: "6px 16px", margin: 0 }}>
      {rows.map(([term, value]) => [
        <dt key={`${term}-t`} className="muted">{term}</dt>,
        <dd key={`${term}-d`} style={{ margin: 0, overflowWrap: "anywhere", whiteSpace: "pre-line" }}>{value || "—"}</dd>,
      ])}
    </dl>
  );
}

function Section({ id, title, wide = false, children }: { id: string; title: string; wide?: boolean; children: ReactNode }) {
  return (
    <section className={`action-card${wide ? " wide" : ""}`} aria-labelledby={id}>
      <h3 id={id}>{title}</h3>
      {children}
    </section>
  );
}

const Empty = ({ text }: { text: string }) => <p className="muted">{text}</p>;

export default function UniversityViewPanel({ view }: { view: UniversityView }) {
  const u = view.university;
  const website = safeWebsite(u.website);
  const applicationsTitle = view.slice === "counselor" ? "Your students' applications" : "Applications";
  return (
    <>
      <div className="portal-title">
        <div>
          <div className="eyebrow">University · {u.university_code}</div>
          <h2>{u.name}</h2>
          <p className="muted">
            {[u.city, u.country.name].filter(Boolean).join(", ")}
            {view.partnership && <> · <span className="badge">{view.partnership.stage_label}</span></>}
          </p>
        </div>
      </div>
      <div className="action-grid">
        <Section id="view-profile" title="Profile" wide>
          <Facts rows={[
            ["University ID", u.university_code],
            ["Institution type", label(INSTITUTION_TYPES, u.institution_type)],
            ["Public / private", label(OWNERSHIP_TYPES, u.ownership_type)],
            ["Country", u.country.name],
            ["State / region", u.state_region],
            ["City", u.city],
            ["Website", website
              ? <a href={website} target="_blank" rel="noopener noreferrer">{website}<span className="visually-hidden"> (opens in a new tab)</span></a>
              : u.website],
            ["Course levels", u.course_levels.join(", ")],
            ["Popular programmes", u.popular_programs.join(", ")],
            ["Rankings", u.rankings.map(rankingText).join("\n")],
            ["Overview", u.overview],
            ["Eligibility", u.eligibility],
          ]} />
        </Section>
        {view.partnership && (
          <Section id="view-partnership" title="Partnership">
            <Facts rows={[
              ["Stage", view.partnership.stage_label + (view.partnership.lost ? " (lost)" : "")],
              ...("manager" in view ? [["Partnership manager", view.manager ? `${view.manager.full_name} · ${view.manager.email}` : "Not assigned yet"] as [string, string]] : []),
            ]} />
          </Section>
        )}
        {view.contacts && (
          <Section id="view-contacts" title="Application contacts" wide={view.contacts.length > 1}>
            {view.contacts.length === 0 ? <Empty text="No shareable contacts yet." /> : (
              <ul className="clean-list" style={{ display: "grid", gap: 12, padding: 0, margin: 0, listStyle: "none" }}>
                {view.contacts.map((c) => (
                  <li key={c.id}>
                    <strong>{c.name}</strong>{c.is_primary && <> <span className="badge">Primary</span></>}
                    <div className="muted">{[c.designation, c.department, c.role?.label].filter(Boolean).join(" · ")}</div>
                    <div style={{ overflowWrap: "anywhere" }}>
                      {[c.email && <a key="e" href={`mailto:${c.email}`}>{c.email}</a>, c.phone, c.whatsapp && `WhatsApp ${c.whatsapp}`].filter(Boolean).map((part, i) => <span key={i}>{i > 0 && " · "}{part}</span>)}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Section>
        )}
        {view.courses && (
          <Section id="view-courses" title="Courses" wide>
            {view.courses.length === 0 ? <Empty text="No active courses yet." /> : (
              <ul style={{ display: "grid", gap: 16, padding: 0, margin: 0, listStyle: "none" }}>
                {view.courses.map((c) => (
                  <li key={c.id}>
                    <h4 style={{ margin: "0 0 6px" }}>{c.title} <span className="badge">{c.level}</span></h4>
                    <Facts rows={[
                      ["Category", c.category],
                      ["Duration", c.duration],
                      ["Tuition fee", money(c.tuition_amount, c.tuition_currency) ?? c.tuition_fee],
                      ["Application fee", money(c.application_fee, c.application_fee_currency)],
                      ["Intakes", c.intakes.length ? c.intakes.join(", ") : c.intake],
                      ["English requirement", englishText(c)],
                      ["Entry requirements", c.entry_requirements],
                      ["Scholarships", c.scholarships.map((s) => `${s.title} (${s.amount})`).join("\n")],
                      ["Application process", c.application_process],
                      ["Deadline", c.deadline && dateText(c.deadline)],
                    ]} />
                  </li>
                ))}
              </ul>
            )}
          </Section>
        )}
        {view.documents && (
          <Section id="view-documents" title="Documents">
            {view.documents.length === 0 ? <Empty text="No shareable documents yet." /> : (
              <ul style={{ display: "grid", gap: 8, padding: 0, margin: 0, listStyle: "none" }}>
                {view.documents.map((d) => (
                  <li key={d.id} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
                    <span><strong>{d.title}</strong> <span className="muted">· {kindLabel(d.kind)} · version {d.current_version}</span></span>
                    <a className="btn secondary small" href={viewDocumentFileUrl(u.id, d.id)} download>Download<span className="visually-hidden"> {d.title}</span></a>
                  </li>
                ))}
              </ul>
            )}
          </Section>
        )}
        {view.applications && (
          <Section id="view-applications" title={applicationsTitle} wide>
            {view.applications.length === 0 ? <Empty text="No applications for this university yet." /> : (
              <div className="table-wrap" tabIndex={0}>
                <table>
                  <caption className="visually-hidden">{applicationsTitle}, {view.applications.length} shown</caption>
                  <thead><tr><th scope="col">Student</th><th scope="col">Reference</th><th scope="col">Intake</th><th scope="col">Status</th><th scope="col">Next action</th><th scope="col">Updated</th></tr></thead>
                  <tbody>
                    {view.applications.map((a) => (
                      <tr key={a.id}>
                        <td>{a.student_name ?? "A student"}</td><td>{a.reference ?? "—"}</td><td>{a.intake}</td><td>{a.status.replaceAll("_", " ")}</td><td>{a.next_action ?? "—"}</td><td><LocalTime value={a.updated_at} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Section>
        )}
      </div>
    </>
  );
}
