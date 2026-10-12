import type { Metadata } from "next";
import Link from "next/link";

import MyManagementDecisions from "@/components/MyManagementDecisions";
import PublicShell from "@/components/PublicShell";
import { ApiError, serverApi } from "@/lib/api";
import { indiaToday } from "@/lib/bdmTravel";
import { MY_DECISIONS_API, MY_DECISIONS_HOME, type MyDecision } from "@/lib/managementDiscussions";
import { dashboardPathFor } from "@/lib/navigation";
import type { User } from "@/lib/types";

// mgmt-027 (M14, MD8): any staff member's management decisions. Like /account/password (ENH-006) this belongs to no one role's portal
// nav, so it is one shared route: the decision notification links here, and mgmt-028's shared
// "Management tasks" page (/account/management-tasks) lists these too. It gates itself (/account/* is outside middleware.ts's matcher); the API returns only the caller's own lines.
const NEXT = encodeURIComponent(MY_DECISIONS_HOME);

export const metadata: Metadata = { title: "Management decisions" };

function Message({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <PublicShell>
      <div className="section">
        <div className="container card">
          <h1>{title}</h1>
          {children}
        </div>
      </div>
    </PublicShell>
  );
}

export default async function MyManagementDecisionsPage() {
  let user: User;
  let items: MyDecision[];
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (error) {
    // Only an explicit 401 means "signed out"; an outage must not send the user to a login that fails too.
    if (!(error instanceof ApiError && error.status === 401)) {
      return (
        <Message title="Temporarily unavailable">
          <p className="muted">We can&apos;t reach EduSphere right now. Try again in a moment.</p>
          <a className="btn" href={MY_DECISIONS_HOME}>Try again</a>
        </Message>
      );
    }
    return (
      <Message title="Sign in required">
        <p className="muted">Sign in to see the management decisions you are responsible for.</p>
        <div className="actions">
          <a className="btn" href={`/it/login?next=${NEXT}`}>IT Training sign in</a>
          <a className="btn secondary" href={`/overseas/login?next=${NEXT}`}>Overseas Education sign in</a>
          <a className="btn secondary" href={`/admin/login?next=${NEXT}`}>Administrator sign in</a>
        </div>
      </Message>
    );
  }
  try {
    items = (await serverApi<{ items: MyDecision[] }>(MY_DECISIONS_API)).items;
  } catch {
    return (
      <Message title="Temporarily unavailable">
        <p className="muted">Your management decisions can&apos;t be loaded right now. Try again in a moment.</p>
        <a className="btn" href={MY_DECISIONS_HOME}>Try again</a>
      </Message>
    );
  }
  const division = user.division === "it" || user.division === "overseas" ? user.division : undefined;
  return (
    <PublicShell division={division}>
      <div className="section compact">
        <div className="container" style={{ maxWidth: 720 }}>
          <Link href={dashboardPathFor(user)} className="muted" style={{ display: "inline-block", padding: "6px 0" }}>← Back to dashboard</Link>
          <h1 style={{ fontSize: 34, marginTop: 14 }}>Management decisions</h1>
          <p className="muted">Decisions management has made you responsible for. Update the status as the work moves on; management sees each change.</p>
          <MyManagementDecisions items={items} today={indiaToday()} />
        </div>
      </div>
    </PublicShell>
  );
}
