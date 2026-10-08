import Link from "next/link";
import type { ReactNode } from "react";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import UniversityActions from "@/components/UniversityActions";
import UniversityAssignForm from "@/components/UniversityAssignForm";
import { serverApi } from "@/lib/api";
import type { User } from "@/lib/types";
import {
  INSTITUTION_TYPES,
  label,
  OWNERSHIP_TYPES,
  POTENTIALS,
  rankingText,
  RELATIONSHIPS,
  shellFor,
  type University,
  UNIVERSITIES_PATH,
  UNIVERSITIES_URL,
  universityPath,
  visibilityLabel,
} from "@/lib/universities";

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
  let user: User, u: University;
  try {
    [user, { university: u }] = await Promise.all([
      serverApi<User>("/api/v1/auth/me"),
      serverApi<{ university: University }>(`${UNIVERSITIES_URL}/${encodeURIComponent(id)}`),
    ]);
  } catch (e) {
    return accessUnavailable(e, "/overseas/login");
  }
  const { nav, roleLabel } = shellFor(user.role);
  const region = [u.state_region, u.country.region].filter(Boolean).join(" · ");
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow"><Link href={UNIVERSITIES_PATH}>University Master</Link> · {u.university_code}</div>
            <h2>{u.name}</h2>
            <p className="muted">{[u.city, u.country.name].filter(Boolean).join(", ")} · <span className="badge">{visibilityLabel(u)}</span></p>
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
              ["State / region", region],
              ["City", u.city],
              ["Website", u.website && <a href={u.website} target="_blank" rel="noopener noreferrer">{u.website}</a>],
              ["Course levels", u.course_levels.join(", ")],
              ["Popular programmes", u.popular_programs.join(", ")],
              ["International office", u.international_office],
              ["Existing relationship", label(RELATIONSHIPS, u.existing_relationship)],
              ["Priority", u.priority],
              ["Partnership potential", label(POTENTIALS, u.partnership_potential)],
              ["Applications", String(u.application_count)],
            ]} />
          </section>
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
        </div>
      </div>
    </PortalShell>
  );
}
