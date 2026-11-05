import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import CollegePlacement from "@/components/CollegePlacement";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { ORG_TYPE_LABEL, type OrgType, safeWebsite } from "@/lib/bdmOrganizations";
import { type College, collegeUrl, COLLEGES_PATH } from "@/lib/recruiterColleges";
import { companyShell, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import type { User } from "@/lib/types";

const COLLEGE_TYPE_LABEL: Record<string, string> = {
  engineering: "Engineering", arts_science: "Arts & Science", management: "Management", medical: "Medical", polytechnic: "Polytechnic", other: "Other",
};

// pob-013 (DEC-SCOPE-410): one college's placement view. A 404 (unknown, archived for the placement team, or not a college-module college)
// or a malformed id (422) is a plain "not found" -- it never says which.
export default async function RecruiterCollegePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let user: User;
  let college: College | null = null;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, RECRUITER_SIGN_IN);
  }
  try {
    college = (await serverApi<{ college: College }>(collegeUrl(id))).college;
  } catch (e) {
    if (!(e instanceof ApiError && (e.status === 404 || e.status === 422))) return accessUnavailable(e, RECRUITER_SIGN_IN);
  }
  const { nav, roleLabel } = companyShell(user.role);
  const site = college ? safeWebsite(college.website) : null;
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <p style={{ margin: "0 0 12px" }}><Link href={COLLEGES_PATH}>← Back to colleges</Link></p>
        {college ? (
          <>
            <div className="portal-title">
              <div>
                <div className="eyebrow">{college.code} · {ORG_TYPE_LABEL[college.org_type as OrgType] ?? college.org_type}</div>
                <h2>{college.name} {college.archived && <span className="badge">Archived</span>}</h2>
                <p className="muted" style={{ margin: 0 }}>
                  {[college.city, college.state].filter(Boolean).join(", ")}
                  {college.affiliation && ` · ${college.affiliation}`}
                  {college.college_type && ` · ${COLLEGE_TYPE_LABEL[college.college_type] ?? college.college_type}`}
                  {college.student_count !== null && ` · ${college.student_count.toLocaleString("en-IN")} students`}
                </p>
                {site && (
                  <p style={{ margin: "4px 0 0" }}>
                    <a href={site} target="_blank" rel="noopener noreferrer">{site}<span className="visually-hidden"> (opens in a new tab)</span></a>
                  </p>
                )}
              </div>
            </div>
            <CollegePlacement orgId={college.id} initial={college} />
          </>
        ) : (
          <div className="action-card">
            <h2>College not found</h2>
            <p>This college does not exist or is not available to you.</p>
          </div>
        )}
      </div>
    </PortalShell>
  );
}
