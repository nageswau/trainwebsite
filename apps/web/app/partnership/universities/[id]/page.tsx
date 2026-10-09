import Link from "next/link";
import type { ReactNode } from "react";

import { accessUnavailable } from "@/components/AccessUnavailable";
import BdmStageHistory from "@/components/BdmStageHistory";
import PartnershipTasksPanel from "@/components/PartnershipTasksPanel";
import PortalShell from "@/components/PortalShell";
import UniversityActions from "@/components/UniversityActions";
import UniversityAgreements from "@/components/UniversityAgreements";
import UniversityAssignForm from "@/components/UniversityAssignForm";
import UniversityCalls from "@/components/UniversityCalls";
import UniversityContacts from "@/components/UniversityContacts";
import UniversityCourses from "@/components/UniversityCourses";
import UniversityFollowUp from "@/components/UniversityFollowUp";
import UniversityDocuments from "@/components/UniversityDocuments";
import UniversityMessages from "@/components/UniversityMessages";
import UniversityStagePanel from "@/components/UniversityStagePanel";
import UniversityTimeline from "@/components/UniversityTimeline";
import VisitTable from "@/components/VisitTable";
import { serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import { COMMS_READERS } from "@/lib/partnershipComms";
import type { StageEvent } from "@/lib/bdmPipeline";
import type { User } from "@/lib/types";
import {
  CONTACT_ROLES_URL,
  type ContactRole,
  contactsUrl,
  INSTITUTION_TYPES,
  label,
  OWNERSHIP_TYPES,
  POTENTIALS,
  rankingText,
  RELATIONSHIP_STRENGTHS,
  RELATIONSHIPS,
  shellFor,
  type University,
  type UniversityContact,
  UNIVERSITIES_PATH,
  universityPath,
  universityUrl,
  visibilityLabel,
} from "@/lib/universities";
import type { MilestonePage } from "@/lib/partnershipMilestones";
import { firstMilestones, firstStageHistory, loadUniversity } from "@/lib/universitiesServer";
import { type Agreement, AGREEMENT_READERS, type AgreementOptions, agreementOptionsUrl, agreementsUrl } from "@/lib/universityAgreements";
import { documentsUrl, type UniversityDocument } from "@/lib/universityDocuments";
import { COMMISSION_ROLES, type CourseOptions, courseOptionsUrl, type CoursePage, coursesUrl } from "@/lib/courseMaster";
import { newVisitPath, PLANNER_ROLES, VISIT_READERS, VISITS_PATH, VISITS_URL, type VisitRow } from "@/lib/visits";
import { TASK_CREATORS, TASK_READERS, TASKS_PATH } from "@/lib/partnershipTasks";

// upc-003: one university's master record -- the §1 fields, rankings, ownership (§27) and catalogue status. Later upc items add their
// own sections (contacts, pipeline, agreements, courses ...) to this page. upc-007: the partnership stage and its history.
// upc-020: §20's Next / Last Action for every reader, and the open follow-ups and tasks for the task readers (TK8; the panel loads
// them itself). upc-026: the Documents section (§28, "everything related to that university in one place"). upc-014: the Agreements
// section (§13). upc-008: the Partnership timeline (§5 expected timeline + §6 milestones) for every reader; editing per
// `can_edit_timeline`.
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

export default async function UniversityPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let user: User, u: University, history: Page<StageEvent> | null, contacts: Page<UniversityContact>, roles: ContactRole[], visits: Page<VisitRow> | null,
    documents: Page<UniversityDocument>, agreements: Page<Agreement> | null, agreementOptions: AgreementOptions | null,
    milestones: MilestonePage | null, courses: CoursePage, courseOptions: CourseOptions | null;
  try {
    [user, u, history, milestones] = await Promise.all([serverApi<User>("/api/v1/auth/me"), loadUniversity(id), firstStageHistory(id), firstMilestones(id)]);
    // upc-006: the contacts this reader may see (the API slices them), and the role list only for those who can edit.
    // upc-010: the latest visits, only for the roles that read visits (VS7; overseas_admin reads the master but not visits).
    // upc-026: the documents this reader may see (the API slices them: shareable only for overseas_admin, no commission agreement).
    // upc-014: agreements only for the roles that read them (AG13), and the form's options only for those who may write them.
    // upc-017: the courses (inactive ones marked) for every reader; the form's scholarship options only for those who may write them.
    [contacts, roles, visits, documents, agreements, agreementOptions, courses, courseOptions] = await Promise.all([
      serverApi<Page<UniversityContact>>(`${contactsUrl(u.id)}?limit=50`),
      u.permissions.can_edit_contacts ? serverApi<{ items: ContactRole[] }>(CONTACT_ROLES_URL).then((r) => r.items) : Promise.resolve([]),
      VISIT_READERS.has(user.role) ? serverApi<Page<VisitRow>>(`${VISITS_URL}?university_id=${u.id}&limit=5`) : Promise.resolve(null),
      serverApi<Page<UniversityDocument>>(documentsUrl(u.id)),
      AGREEMENT_READERS.has(user.role) ? serverApi<Page<Agreement>>(agreementsUrl(u.id)) : Promise.resolve(null),
      u.permissions.can_manage_agreements ? serverApi<AgreementOptions>(agreementOptionsUrl(u.id)) : Promise.resolve(null),
      serverApi<CoursePage>(`${coursesUrl(u.id)}?include_inactive=true&limit=50`),
      u.permissions.can_edit ? serverApi<CourseOptions>(courseOptionsUrl(u.id)) : Promise.resolve(null),
    ]);
  } catch (e) {
    return accessUnavailable(e, "/overseas/login");
  }
  const { nav, roleLabel } = shellFor(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow"><Link href={UNIVERSITIES_PATH}>University Master</Link> · {u.university_code}</div>
            <h2>{u.name}</h2>
            <p className="muted">{[u.city, u.country.name].filter(Boolean).join(", ")} · <span className="badge">{visibilityLabel(u)}</span>
              {u.relationship_strength && <> <span className="badge">Relationship: {label(RELATIONSHIP_STRENGTHS, u.relationship_strength)}</span></>}</p>
          </div>
          {u.permissions.can_edit && <Link className="btn" href={universityPath(u.id, true)}>Edit</Link>}
        </div>
        <div className="action-grid">
          <section className="action-card wide" aria-labelledby="uni-profile">
            <h3 id="uni-profile">Profile</h3>
            <Facts rows={[
              ["University ID", u.university_code],
              ["Institution type", label(INSTITUTION_TYPES, u.institution_type)],
              ["Public / private", label(OWNERSHIP_TYPES, u.ownership_type)],
              ["Country", u.country.name],
              ["World region", u.country.region],
              ["State / region", u.state_region],
              ["City", u.city],
              ["Website", u.website && <a href={u.website} target="_blank" rel="noopener noreferrer">{u.website}</a>],
              ["Course levels", u.course_levels.join(", ")],
              ["Popular programmes", u.popular_programs.join(", ")],
              ["International office", u.international_office],
              ["Existing relationship", label(RELATIONSHIPS, u.existing_relationship)],
              ["Priority", u.priority],
              ["Partnership potential", label(POTENTIALS, u.partnership_potential)],
              ["Relationship strength", u.relationship_strength && label(RELATIONSHIP_STRENGTHS, u.relationship_strength)],
              ["Applications", String(u.application_count)],
            ]} />
          </section>
          <section className="action-card wide" aria-labelledby="uni-follow-ups">
            <h3 id="uni-follow-ups">Follow-ups &amp; tasks</h3>
            <UniversityFollowUp followUp={u.follow_up} />
            {TASK_READERS.has(user.role) && (
              <>
                {/* QA-01: remounted after each stage change (the page refreshes), so a new auto-task shows without a reload */}
                <PartnershipTasksPanel key={`tasks|${u.pipeline.changed_at}`} role={user.role} university={{ id: u.id, name: u.name }} canAdd={TASK_CREATORS.has(user.role) && u.permissions.can_edit_contacts} />
                <div className="actions" style={{ marginTop: 12 }}><Link className="btn ghost small" href={TASKS_PATH}>All follow-ups &amp; tasks</Link></div>
              </>
            )}
          </section>
          <UniversityStagePanel university={u} />
          {/* remounted after each stage change (the page refreshes), so it starts from the new first page */}
          <BdmStageHistory key={`${u.pipeline.changed_at}|${u.pipeline.lost?.at ?? ""}`} orgId={u.id} initial={history} version={0} url={universityUrl(u.id, "stage-history")} />
          {/* upc-008: remounted after each stage change, so a move into Proposal Sent shows Proposal achieved (MS4) */}
          <UniversityTimeline key={`timeline|${u.pipeline.changed_at}`} universityId={u.id} expected={u.expected} canEdit={u.permissions.can_edit_timeline} initial={milestones} />
          <UniversityContacts universityId={u.id} contacts={contacts.items} roles={roles} canEdit={u.permissions.can_edit_contacts} />
          <UniversityCourses universityId={u.id} page={courses} options={courseOptions} canSetCommission={COMMISSION_ROLES.has(user.role)} />
          {agreements && (
            <UniversityAgreements universityId={u.id} agreements={agreements.items} options={agreementOptions} canManage={u.permissions.can_manage_agreements} />
          )}
          <UniversityDocuments universityId={u.id} documents={documents.items} canManage={u.permissions.can_manage_documents} />
          {/* upc-012 (UC3): calls and messages, for the partnership roles only; the contacts are the recipients */}
          {COMMS_READERS.has(user.role) && (
            <>
              <UniversityCalls universityId={u.id} canWrite={u.permissions.can_edit_contacts}
                contacts={contacts.items.map((c) => ({ id: c.id, name: c.name, phone: c.phone ?? c.whatsapp }))} />
              <UniversityMessages universityId={u.id} contacts={contacts.items} canWrite={u.permissions.can_edit_contacts} />
            </>
          )}
          {visits && (
            <section className="action-card wide" aria-labelledby="uni-visits">
              <h3 id="uni-visits">Visits</h3>
              {visits.total === 0 ? <p className="muted">No visits planned yet.</p> : <VisitTable page={visits} label="Visits to this university" showUniversity={false} />}
              <div className="actions" style={{ marginTop: 12 }}>
                {PLANNER_ROLES.has(user.role) && u.permissions.can_edit_contacts && <Link className="btn secondary small" href={newVisitPath(u.id)}>Plan a visit</Link>}
                {visits.total > visits.items.length && <Link className="btn ghost small" href={`${VISITS_PATH}?university_id=${u.id}`}>All {visits.total} visits</Link>}
              </div>
            </section>
          )}
          <section className="action-card" aria-labelledby="uni-rankings">
            <h3 id="uni-rankings">Rankings</h3>
            {u.rankings.length ? <ul className="list-clean">{u.rankings.map((r) => <li key={rankingText(r)}>{rankingText(r)}</li>)}</ul>
              : <p className="muted">No rankings recorded.</p>}
          </section>
          <section className="action-card" aria-labelledby="uni-owners">
            <h3 id="uni-owners">EduSphere owner</h3>
            <Facts rows={[
              ["Primary manager", u.primary_manager ? `${u.primary_manager.full_name}${u.primary_manager.active ? "" : " (inactive)"}` : "Unassigned"],
              ["Backup manager", u.backup_manager ? `${u.backup_manager.full_name}${u.backup_manager.active ? "" : " (inactive)"}` : "None"],
            ]} />
            {u.permissions.can_assign && <div style={{ marginTop: 12 }}><UniversityAssignForm university={u} /></div>}
          </section>
          <section className="action-card" aria-labelledby="uni-catalogue">
            <h3 id="uni-catalogue">Public catalogue</h3>
            <p className="muted" style={{ marginTop: 0 }}>
              {!u.active ? "Inactive: hidden from the catalogue and read-only." : u.catalogue_visible
                ? "Published: students and agents can find this university."
                : "Internal: only EduSphere staff can see this university."}
            </p>
            {u.overview ? <p style={{ whiteSpace: "pre-line" }}>{u.overview}</p> : <p className="muted">No overview yet (needed to publish).</p>}
            <UniversityActions university={u} />
          </section>
          <section className="action-card" aria-labelledby="uni-bdm-links">
            <h3 id="uni-bdm-links">Linked BDM organizations</h3>
            {/* upc-004 UD11: text only -- BDM records open in the BDM workspace, not here */}
            {u.linked_bdm_organizations.length ? (
              <ul className="list-clean">
                {u.linked_bdm_organizations.map((o) => (
                  <li key={o.id}>
                    {o.code} · {o.name}, {o.city} · BDM {o.assigned_bdm_name}{o.archived ? " · Archived" : ""}
                  </li>
                ))}
              </ul>
            ) : <p className="muted">No BDM organization is linked to this university.</p>}
          </section>
        </div>
      </div>
    </PortalShell>
  );
}
