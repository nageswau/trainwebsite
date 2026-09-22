import SchoolGradeHistory, { loadGradeHistory } from "@/components/SchoolGradeHistory";
import SchoolStudentTimeline, { loadStudentTimeline } from "@/components/SchoolStudentTimeline";
import SchoolTransferHistory, { loadTransferHistory } from "@/components/SchoolTransferHistory";
import SchoolTransferRequestForm from "@/components/SchoolTransferRequestForm";
import PortfolioPanel from "@/components/PortfolioPanel";
import { formatDate } from "@/components/SchoolChildOverview";
import { serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import type { SchoolRef, TransferRequest } from "@/lib/transfers";
import { loadPortfolio } from "@/lib/portfolio";

// Shared read-only student header + Journey Timeline, reused across every School role that
// can open one student's page within their own SCH-001 scope: Teacher (assigned), School
// Coordinator and Principal (own institution). Each role keeps its own thin page/route
// (matching this app's existing per-role-route convention -- see SchoolServiceDeliverySummary
// for the same reuse pattern across dashboards) -- only this presentational piece is shared,
// so no role gains another role's write actions by using it.
// ENH-004: `showGradeHistory` (default off, so the Principal and Teacher pages are unchanged)
// adds the read-only grade-history card for the Coordinator. Both reads start together.
// ENH-005: `showTransfer` (default off, for the same reason) adds the coordinator's transfer history card and a "Request a transfer"
// disclosure. The disclosure sits right under the header, collapsed: it is a rare, consequential action, so it stays out of the way of the
// record, but at the end of a long timeline it was hard to find on a phone (browser QA N4). Its destinations and this student's pending
// request are read here, in the same Promise.all, so opening it needs no client round-trip and no loading state.

type Student = { id: string; student_code: string; full_name: string; date_of_birth: string | null; grade_or_class: string | null };

export default async function SchoolStudentDetailPanel({ student, backHref, backLabel, showGradeHistory = false, showTransfer = false }: { student: Student; backHref: string; backLabel: string; showGradeHistory?: boolean; showTransfer?: boolean }) {
  const [timeline, gradeHistory, transferHistory, destinations, pendingPage, portfolio] = await Promise.all([
    loadStudentTimeline(student.id).catch(() => null),
    showGradeHistory ? loadGradeHistory(student.id).catch(() => null) : Promise.resolve(null),
    showTransfer ? loadTransferHistory(student.id) : Promise.resolve([]),
    showTransfer ? serverApi<SchoolRef[]>("/api/v1/school/transfer-destinations").catch(() => null) : Promise.resolve([]),
    showTransfer ? serverApi<Page<TransferRequest>>("/api/v1/school/transfer-requests?status=pending&limit=100").catch(() => null) : Promise.resolve(null),
    loadPortfolio(student.id).catch(() => null),
  ]);
  // A school has at most 50 open requests, so one page of pending requests always contains this student's if it has one. If the lookup
  // failed the form is still offered: the server refuses a duplicate with a clear message.
  const pending = pendingPage?.items.find((r) => r.student_id === student.id) ?? null;
  return (
    <div className="portal-content">
      <div className="card">
        <h2>{student.full_name} <span className="muted" style={{ fontSize: 14 }}>({student.student_code})</span></h2>
        <p><strong>Grade/Class:</strong> {student.grade_or_class || "-"}</p>
        <p><strong>Date of birth:</strong> {formatDate(student.date_of_birth)}</p>
        {pending && <p><span className="status pending">Transfer requested</span> to {pending.to_school.name}</p>}
        <a className="btn secondary" href={backHref}>{backLabel}</a>
      </div>
      {showTransfer && (
        <details className="card">
          <summary><strong>Request a transfer</strong></summary>
          <SchoolTransferRequestForm studentId={student.id} destinations={destinations} pending={pending ? { to_school_name: pending.to_school.name, created_at: pending.created_at } : null} />
        </details>
      )}
      {showGradeHistory && (
        <div className="card">
          <h3>Grade history</h3>
          {gradeHistory ? <SchoolGradeHistory history={gradeHistory.history} /> : <p className="muted">Grade history is unavailable right now.</p>}
        </div>
      )}
      {showTransfer && <SchoolTransferHistory history={transferHistory} />}
      <div className="card">
        <h3>Journey timeline</h3>
        {timeline ? <SchoolStudentTimeline events={timeline.events} /> : <p className="muted">Timeline is unavailable right now.</p>}
      </div>
      {portfolio ? <PortfolioPanel data={portfolio} /> : <div className="card"><h3>Digital Portfolio</h3><p className="muted">Portfolio is unavailable right now.</p></div>}
    </div>
  );
}
