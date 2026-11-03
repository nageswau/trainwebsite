import Link from "next/link";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import LocalTime from "@/components/LocalTime";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { HR_STUDENTS_PATH } from "@/lib/hrStudents";
import { apiQuery, formatDay, HR_QUEUE_API, HR_QUEUE_PATH, HR_REVIEW_STAGES, isStage, listQuery, OPEN_STAGES, PAGE_SIZE, STAGE_LABELS, type HrQueue } from "@/lib/hrReviews";
import { PORTAL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

// itc-027 (DEC-SCOPE-354 H4): HR's review queue -- the resume reviews assigned to the signed-in HR user (open ones by default, or one
// stage), newest activity first, each linking to the HR student page where the review is worked. The API scopes it to the caller.
export default async function HrReviewQueuePage({ searchParams }: { searchParams: Record<string, string | string[] | undefined> }) {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/it/login");
  }
  if (user.role !== "hr_team") return accessDenied(user, "HR role required");
  const stage = isStage(searchParams.stage) ? searchParams.stage : "";
  const requested = Number(typeof searchParams.page === "string" ? searchParams.page : "1");
  const page = Number.isInteger(requested) && requested >= 1 && requested <= 10000 ? requested : 1;
  let queue: HrQueue | null = null;
  try {
    queue = await serverApi<HrQueue>(`${HR_QUEUE_API}${apiQuery({ stage, page })}`);
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return accessUnavailable(e, "/it/login");
  }
  const pages = queue ? Math.max(1, Math.ceil(queue.total / PAGE_SIZE)) : 1;
  const open = queue ? OPEN_STAGES.reduce((sum, s) => sum + queue.counts[s], 0) : 0;
  return (
    <PortalShell nav={PORTAL_NAV["it/hr"]} roleLabel="HR Team" userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Resume reviews</div>
            <h2>Review Queue</h2>
            <p className="muted">Resumes students shared with HR that are assigned to you. Open a student to review the resume, tick the checklist and move the stage.</p>
          </div>
        </div>
        <div className="action-card">
          {queue && (
            <nav aria-label="Stages" style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 12 }}>
              <Link className={`btn small ${stage ? "secondary" : ""}`} aria-current={stage ? undefined : "page"} href={HR_QUEUE_PATH}>All open ({open})</Link>
              {HR_REVIEW_STAGES.map((s) => (
                <Link key={s} className={`btn small ${stage === s ? "" : "secondary"}`} aria-current={stage === s ? "page" : undefined} href={`${HR_QUEUE_PATH}${listQuery({ stage: s })}`}>
                  {STAGE_LABELS[s]} ({queue.counts[s]})
                </Link>
              ))}
            </nav>
          )}
          {!queue ? (
            <p className="form-error" role="alert">The review queue is unavailable right now. Please try again.</p>
          ) : queue.items.length === 0 ? (
            <p className="muted">{stage ? `No reviews at “${STAGE_LABELS[stage]}”.` : "No open reviews are assigned to you."}</p>
          ) : (
            <>
              <p className="muted" aria-live="polite">{queue.total} review{queue.total === 1 ? "" : "s"}</p>
              <div className="table-wrap">
                <table className="table stack compact" aria-label="Review queue">
                  <thead><tr><th scope="col">Student</th><th scope="col">Student ID</th><th scope="col">Stage</th><th scope="col">Resume</th><th scope="col">Screening</th><th scope="col">Updated</th></tr></thead>
                  <tbody>
                    {queue.items.map((t) => (
                      <tr key={t.id}>
                        <th scope="row" data-label="Student">
                          <Link href={`${HR_STUDENTS_PATH}/${encodeURIComponent(t.student.id)}`}>{t.student.full_name}</Link>
                        </th>
                        <td data-label="Student ID">{t.student.student_code ?? "—"}</td>
                        <td data-label="Stage">{t.stage_label}</td>
                        <td data-label="Resume">Version {t.resume_version}</td>
                        <td data-label="Screening">{formatDay(t.screening_date)}</td>
                        <td data-label="Updated"><LocalTime value={t.updated_at} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {pages > 1 && (
                <nav aria-label="Pages" style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 12 }}>
                  {page > 1 && <Link className="btn small secondary" href={`${HR_QUEUE_PATH}${listQuery({ stage, page: page - 1 })}`}>Previous</Link>}
                  <span className="muted">Page {page} of {pages}</span>
                  {page < pages && <Link className="btn small secondary" href={`${HR_QUEUE_PATH}${listQuery({ stage, page: page + 1 })}`}>Next</Link>}
                </nav>
              )}
            </>
          )}
        </div>
      </div>
    </PortalShell>
  );
}
