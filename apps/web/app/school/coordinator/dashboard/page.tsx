import Link from "next/link";
import PortalShell from "@/components/PortalShell";
import SchoolServiceDeliverySummary from "@/components/SchoolServiceDeliverySummary";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

type DashboardPayload = {
  student_count: number;
  upcoming_activities: { id: string; title: string; scheduled_at: string }[];
};

// SCH-001: Coordinator's landing view -- roster size and upcoming activities, with quick
// links to the two things they actually do here (add students, schedule things).
export default async function SchoolCoordinatorDashboardPage() {
  let user: User;
  let data: DashboardPayload;
  try {
    [user, data] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<DashboardPayload>("/api/v1/school/dashboard")]);
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
  return (
    <PortalShell nav={SCHOOL_NAV.coordinator} roleLabel="School Coordinator" userName={user.full_name}>
      <div className="portal-content">
        <div className="card">
          <h2>Your school</h2>
          {data.student_count === 0 ? (
            <p className="muted">No students yet. Add your first student, or upload your roster in bulk.</p>
          ) : (
            <p>{data.student_count} student{data.student_count === 1 ? "" : "s"} on your roster.</p>
          )}
          <div className="field" style={{ flexDirection: "row", gap: 12 }}>
            <Link className="btn" href="/school/coordinator/students">Go to student roster</Link>
            <Link className="btn secondary" href="/school/coordinator/students/bulk-upload">Go to bulk upload</Link>
            <a className="btn secondary" href="/school/coordinator/activities">Go to activities</a>
            <a className="btn secondary" href="/school/coordinator/reports">Go to reports</a>
          </div>
        </div>
        <div className="card">
          <h2>Upcoming activities</h2>
          {data.upcoming_activities.length === 0 ? (
            <p className="muted">Nothing scheduled yet.</p>
          ) : (
            <table className="table">
              <thead>
                <tr><th>Title</th><th>When</th></tr>
              </thead>
              <tbody>
                {data.upcoming_activities.map((a) => (
                  <tr key={a.id}><td>{a.title}</td><td>{new Date(a.scheduled_at).toLocaleString()}</td></tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <SchoolServiceDeliverySummary />
      </div>
    </PortalShell>
  );
}
