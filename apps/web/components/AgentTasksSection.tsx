"use client";

import Link from "next/link";
import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import AgentTasksBlock from "./AgentTasksBlock";
import { parseView, TASK_VIEWS, VIEW_LABELS } from "@/lib/agentTasks";
import type { User } from "@/lib/types";

// AGN-016 (DEC-SCOPE-053): the agency Tasks page. The view lives in the URL (?view=, like Applications' ?status=), so it is
// shareable and Back works; staff see only their assigned students' tasks (G4). A non-agency viewer (Super Admin) gets a note.
function Views() {
  const view = parseView(useSearchParams().get("view"));
  return (
    <>
      <nav aria-label="Task views" className="actions" style={{ gap: 8, margin: "16px 0" }}>
        {TASK_VIEWS.map((v) => (
          <Link key={v} href={`/overseas/agent/tasks?view=${v}`} className={v === view ? "btn small" : "btn secondary small"} aria-current={v === view ? "page" : undefined}>
            {VIEW_LABELS[v]}
          </Link>
        ))}
      </nav>
      <AgentTasksBlock key={view} view={view} />
    </>
  );
}

export default function AgentTasksSection({ user }: { user: User }) {
  const member = user.role === "agent";
  const intro = !member
    ? "Agency tasks are managed by the agency's own Masters and Staff."
    : user.agent_member_role === "staff"
      ? "Follow-ups on the students assigned to you, earliest due first."
      : "Every follow-up across your agency, earliest due first.";
  return (
    <div className="portal-content">
      <div className="portal-title">
        <div>
          <div className="eyebrow">Workspace</div>
          <h2>Tasks &amp; follow-ups</h2>
          <p className="muted">{intro}</p>
        </div>
      </div>
      {member && (
        <Suspense fallback={<p className="muted">Loading tasks…</p>}>
          <Views />
        </Suspense>
      )}
    </div>
  );
}
