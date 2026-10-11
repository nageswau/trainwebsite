import Link from "next/link";

import { quickActionsFor } from "@/lib/recruiterDashboard";

// rec-032 (EVID-018 §1 Quick Actions, DB9): the create forms the caller may use. The API stays the gate on every form.
export default function RecruiterQuickActions({ role }: { role: string }) {
  const actions = quickActionsFor(role);
  if (!actions.length) return null;
  const schedules = actions.some((a) => a.href === "/recruiter/companies");
  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <h3 id="quick-actions-title">Quick actions</h3>
      <nav className="actions rec-quick-actions" aria-labelledby="quick-actions-title" style={{ flexWrap: "wrap" }}>
        {actions.map((a) => (
          <Link key={a.label} className="btn secondary small" href={a.href}>{a.label}</Link>
        ))}
      </nav>
      {schedules && <p className="muted" style={{ margin: "8px 0 0" }}>Meetings are scheduled from a company&apos;s page, and interviews from a candidate on a requirement.</p>}
    </div>
  );
}
