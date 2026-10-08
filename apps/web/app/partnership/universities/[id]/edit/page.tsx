import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import UniversityForm from "@/components/UniversityForm";
import { serverApi } from "@/lib/api";
import type { User } from "@/lib/types";
import { shellFor, type University, universityPath, UNIVERSITIES_URL } from "@/lib/universities";

// upc-003 (AC1, AC4): edit a university's master record. Only someone the API lets edit sees the form; the API re-checks on save.
export default async function EditUniversityPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let user: User, university: University;
  try {
    [user, { university }] = await Promise.all([
      serverApi<User>("/api/v1/auth/me"),
      serverApi<{ university: University }>(`${UNIVERSITIES_URL}/${encodeURIComponent(id)}`),
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
            <div className="eyebrow"><Link href={universityPath(university.id)}>{university.university_code}</Link></div>
            <h2>Edit {university.name}</h2>
          </div>
        </div>
        {university.permissions.can_edit ? (
          <UniversityForm university={university} />
        ) : (
          <p className="empty" role="status">
            {university.active ? "Only the university's partnership managers can edit it." : "Reactivate this university before editing it."}{" "}
            <Link href={universityPath(university.id)}>Back to the university</Link>
          </p>
        )}
      </div>
    </PortalShell>
  );
}
