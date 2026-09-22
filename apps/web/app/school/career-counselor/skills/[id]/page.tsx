import Link from "next/link";

import PortalShell from "@/components/PortalShell";
import SchoolSkillAttendance from "@/components/SchoolSkillAttendance";
import SchoolSkillBatchHeader from "@/components/SchoolSkillBatchHeader";
import SchoolSkillEnrolments from "@/components/SchoolSkillEnrolments";
import SchoolSkillScores from "@/components/SchoolSkillScores";
import { ApiError, serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { PortfolioStudent, SkillBatchDetail } from "@/lib/skills";
import type { User } from "@/lib/types";

// ENH-011: one batch -- details, students, sessions & attendance, assessments & scores, in the order the work is done. Read on the
// server; each section re-reads it with router.refresh() after a change. A batch outside the counselor's portfolio is a 404.
export default async function SchoolSkillBatchPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let user: User;
  let batch: SkillBatchDetail;
  let students: PortfolioStudent[];
  try {
    [user, batch, students] = await Promise.all([
      serverApi<User>("/api/v1/auth/me"),
      serverApi<SkillBatchDetail>(`/api/v1/school/career-counselor/skill-batches/${encodeURIComponent(id)}`),
      serverApi<PortfolioStudent[]>("/api/v1/school/portfolio-students"),
    ]);
  } catch (e) {
    const missing = e instanceof ApiError && (e.status === 404 || e.status === 422);
    return (
      <div className="section">
        <div className="container card">
          <h1>{missing ? "Batch not found" : "Access unavailable"}</h1>
          <p>{missing ? "This skills batch does not exist, or it belongs to a school outside your portfolio." : e instanceof Error ? e.message : "Unable to load this workspace"}</p>
          {missing ? <Link className="btn" href="/school/career-counselor/skills">Back to skills batches</Link> : <a className="btn" href="/overseas/login">Return to login</a>}
        </div>
      </div>
    );
  }
  return (
    <PortalShell nav={SCHOOL_NAV["career-counselor"]} roleLabel="Career Counselor" userName={user.full_name}>
      {/* `minmax(0, 1fr)`: a grid item's default `min-width: auto` let the roster table's 650px min-width widen the whole page on a
          phone (browser QA-01); with it the card stays at screen width and the table scrolls inside `.table-wrap`. */}
      <div className="portal-content" style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: 20 }}>
        <Link href="/school/career-counselor/skills">← All skills batches</Link>
        <SchoolSkillBatchHeader batch={batch} />
        <SchoolSkillEnrolments batch={batch} students={students.filter((s) => s.school_id === batch.school.id)} />
        <SchoolSkillAttendance batch={batch} />
        <SchoolSkillScores batch={batch} />
      </div>
    </PortalShell>
  );
}
