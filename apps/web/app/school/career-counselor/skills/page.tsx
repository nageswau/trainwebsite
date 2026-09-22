import PortalShell from "@/components/PortalShell";
import SchoolSkillBatchesPanel from "@/components/SchoolSkillBatchesPanel";
import type { Page } from "@/lib/apiErrors";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { PortfolioStudent, SkillBatch } from "@/lib/skills";
import type { SchoolRef } from "@/lib/transfers";
import type { User } from "@/lib/types";

// ENH-011: the Career Counselor's Soft Skills / Digital Skills batches. Everything is read on the server (first paint needs no
// spinner); the schools a batch can be created for are the ones the counselor's portfolio students belong to.
export default async function SchoolCareerCounselorSkillsPage() {
  let user: User;
  let batches: Page<SkillBatch>;
  let students: PortfolioStudent[];
  try {
    [user, batches, students] = await Promise.all([
      serverApi<User>("/api/v1/auth/me"),
      serverApi<Page<SkillBatch>>("/api/v1/school/career-counselor/skill-batches?limit=25&offset=0"),
      serverApi<PortfolioStudent[]>("/api/v1/school/portfolio-students"),
    ]);
  } catch (e) {
    return (
      <div className="section">
        <div className="container card">
          <h1>Access unavailable</h1>
          <p>{e instanceof Error ? e.message : "Unable to load this workspace"}</p>
          <a className="btn" href="/overseas/login">Return to login</a>
        </div>
      </div>
    );
  }
  const schools: SchoolRef[] = [...new Map(students.map((s) => [s.school_id, { id: s.school_id, name: s.school_name }])).values()].sort((a, b) => a.name.localeCompare(b.name));
  return (
    <PortalShell nav={SCHOOL_NAV["career-counselor"]} roleLabel="Career Counselor" userName={user.full_name}>
      <SchoolSkillBatchesPanel initial={batches} schools={schools} />
    </PortalShell>
  );
}
