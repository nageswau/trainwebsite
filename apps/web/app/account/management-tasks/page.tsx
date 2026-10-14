import type { Metadata } from "next";
import Link from "next/link";

import MyManagementDecisions from "@/components/MyManagementDecisions";
import MyManagementMeetings from "@/components/MyManagementMeetings";
import MyManagementTasks from "@/components/MyManagementTasks";
import PublicShell from "@/components/PublicShell";
import { ApiError, serverApi } from "@/lib/api";
import { indiaToday } from "@/lib/bdmTravel";
import { MY_DECISIONS_API, type MyDecision } from "@/lib/managementDiscussions";
import { MY_MEETINGS_API, type MyMeeting } from "@/lib/managementMeetings";
import { MY_TASKS_API, MY_TASKS_HOME, type MyTaskPage } from "@/lib/managementTasks";
import { dashboardPathFor } from "@/lib/navigation";
import type { User } from "@/lib/types";

// mgmt-028 (M14, MT9/MT10/MT14): any staff member's Management tasks -- the tasks management assigned them, in the §28 bands, then the
// mgmt-027 decisions they are responsible for. One shared route (like /account/password) that every staff portal's sidebar links to.
// It gates itself (/account/* is outside middleware.ts's matcher); the API returns only the caller's own tasks and decisions.
// mgmt-029 (MM12): then the management meetings they are invited to (#meetings, the notifications' link).
const NEXT = encodeURIComponent(MY_TASKS_HOME);

export const metadata: Metadata = { title: "Management tasks" };

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

function Unavailable({ what }: { what: string }) {
  return (
    <Message title="Temporarily unavailable">
      <p className="muted">{what} Try again in a moment.</p>
      <a className="btn" href={MY_TASKS_HOME}>Try again</a>
    </Message>
  );
}

export default async function MyManagementTasksPage() {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (error) {
    // Only an explicit 401 means "signed out"; an outage must not send the user to a login that fails too.
    if (!(error instanceof ApiError && error.status === 401)) return <Unavailable what="We can't reach EduSphere right now." />;
    return (
      <Message title="Sign in required">
        <p className="muted">Sign in to see the management tasks assigned to you.</p>
        <div className="actions">
          <a className="btn" href={`/it/login?next=${NEXT}`}>IT Training sign in</a>
          <a className="btn secondary" href={`/overseas/login?next=${NEXT}`}>Overseas Education sign in</a>
          <a className="btn secondary" href={`/admin/login?next=${NEXT}`}>Administrator sign in</a>
        </div>
      </Message>
    );
  }
  let tasks: MyTaskPage;
  let decisions: MyDecision[];
  let meetings: MyMeeting[] | null; // mgmt-029 (MM12): a failed read only blanks this section
  try {
    [tasks, { items: decisions }, meetings] = await Promise.all([
      serverApi<MyTaskPage>(MY_TASKS_API),
      serverApi<{ items: MyDecision[] }>(MY_DECISIONS_API),
      serverApi<{ items: MyMeeting[] }>(MY_MEETINGS_API).then((page) => page.items, () => null),
    ]);
  } catch {
    return <Unavailable what="Your management tasks can't be loaded right now." />;
  }
  const division = user.division === "it" || user.division === "overseas" ? user.division : undefined;
  return (
    <PublicShell division={division}>
      <div className="section compact">
        <div className="container" style={{ maxWidth: 760 }}>
          <Link href={dashboardPathFor(user)} className="muted" style={{ display: "inline-block", padding: "6px 0" }}>← Back to dashboard</Link>
          <h1 style={{ fontSize: 34, marginTop: 14 }}>Management tasks</h1>
          <p className="muted">Tasks management has assigned to you. Update the status as the work moves on; management sees each change.</p>
          <MyManagementTasks data={tasks} />
          <h2 style={{ marginTop: 32 }}>Decisions</h2>
          <p className="muted">Management decisions you are responsible for.</p>
          <MyManagementDecisions items={decisions} today={indiaToday()} />
          <h2 id="meetings" style={{ marginTop: 32 }}>Meetings</h2>
          <p className="muted">Management meetings you are invited to, from the last week on.</p>
          {meetings === null ? <p className="form-error" role="alert">Your meetings can&apos;t be loaded right now. Try again in a moment.</p> : <MyManagementMeetings items={meetings} />}
        </div>
      </div>
    </PublicShell>
  );
}
