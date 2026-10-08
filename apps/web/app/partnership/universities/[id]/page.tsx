import Link from "next/link";
import type { ReactNode } from "react";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import UniversityActions from "@/components/UniversityActions";
import UniversityAssignForm from "@/components/UniversityAssignForm";
import UniversityContacts from "@/components/UniversityContacts";
import VisitTable from "@/components/VisitTable";
import { serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
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
  visibilityLabel,
} from "@/lib/universities";
import { loadUniversity } from "@/lib/universitiesServer";
import { newVisitPath, PLANNER_ROLES, VISIT_READERS, VISITS_PATH, VISITS_URL, type VisitRow } from "@/lib/visits";

// upc-003: one university's master record -- the §1 fields, rankings, ownership (§27) and catalogue status. Later upc items add their
// own sections (contacts, pipeline, agreements, courses ...) to this page.
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
  let user: User, u: University, contacts: Page<UniversityContact>, roles: ContactRole[], visits: Page<VisitRow> | null;
  try {
    [user, u] = await Promise.all([serverApi<User>("/api/v1/auth/me"), loadUniversity(id)]);
    // upc-006: the contacts this reader may see (the API slices them), and the role list only for those who can edit.
    // upc-010: the latest visits, only for the roles that read visits (VS7; overseas_admin reads the master but not visits).
    [contacts, roles, visits] = await Promise.all([
      serverApi<Page<UniversityContact>>(`${contactsUrl(u.id)}?limit=50`),
      u.permissions.can_edit_contacts ? serverApi<{ items: ContactRole[] }>(CONTACT_ROLES_URL).then((r) => r.items) : Promise.resolve([]),
      VISIT_READERS.has(user.role) ? serverApi<Page<VisitRow>>(`${VISITS_URL}?university_id=${u.id}&limit=5`) : Promise.resolve(null),
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
          <UniversityContacts universityId={u.id} contacts={contacts.items} roles={roles} canEdit={u.permissions.can_edit_contacts} />
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
