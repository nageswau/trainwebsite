import PortalShell from "@/components/PortalShell";
import SchoolServiceDeliverySummary from "@/components/SchoolServiceDeliverySummary";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

type Student = { id: string; full_name: string; date_of_birth: string | null; grade_or_class: string | null };

// SCH-001: a Parent's view of their own child(ren) -- own institution AND own child(ren)
// only, read-only (SCH-001-AC03). One card per linked child; no switcher control needed
// since every child's summary is already visible at once, not paged behind a picker.
export default async function SchoolParentDashboardPage() {
  let user: User;
  let children: Student[];
  try {
    [user, children] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<Student[]>("/api/v1/school/students")]);
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
    <PortalShell nav={SCHOOL_NAV.parent} roleLabel="Parent" userName={user.full_name}>
      <div className="portal-content">
        {children.length === 0 ? (
          <div className="card">
            <p className="muted">No child linked to your account yet. Contact your school to get set up.</p>
          </div>
        ) : (
          children.map((c) => (
            <div className="card" key={c.id}>
              <h2>{c.full_name}</h2>
              <p><strong>Grade/Class:</strong> {c.grade_or_class || "-"}</p>
              <p><strong>Date of birth:</strong> {c.date_of_birth || "-"}</p>
            </div>
          ))
        )}
        <SchoolServiceDeliverySummary />
      </div>
    </PortalShell>
  );
}
