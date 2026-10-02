// AGN-002 (DEC-SCOPE-040): what the agency staff screens (AgentStaffPanel, AgentStaffRow, AgentStaffCreateForm) share.

import type { AgentPermissions } from "@/lib/types";

export const STAFF_URL = "/api/v1/workflows/overseas/agent/team/staff";

export type StaffMember = { id: string; code: string; full_name: string; email: string; phone: string | null; status: "active" | "deactivated"; setup: "pending_setup" | "link_expired" | null; permissions: AgentPermissions };

// Browser QA-05/QA-06: how the staff screens word a failed request. A server error (5xx) carries no useful detail, so it says to
// retry; a dropped connection only promises a kept entry where something was typed (add / edit), not for a button action.
export function staffFailure(outcome: { message: string; status?: number }, keepsEntry: boolean): string {
  if (outcome.status === undefined) return keepsEntry ? outcome.message : "Couldn't reach the server. Check your connection and try again.";
  if (outcome.status >= 500) return "The server couldn't complete this. Please try again in a moment.";
  return outcome.message;
}

// AGN-021 (DEC-SCOPE-046): one line of a staff member's activity, as GET …/staff/{id}/activity returns it.
export type StaffActivityItem = { id: string; at: string; action: string; subject: string; fields: string[] | null };

const ACTIVITY_LABELS: Record<string, string> = {
  "agent_student.create": "Created a student record",
  "agent_student.update": "Edited a student record",
  "agent_student.duplicate_override": "Saved a student record despite a duplicate warning",
  "agent_student.counseling": "Recorded counseling",
  // AGN-007 (DEC-SCOPE-049, browser QA-09): shortlist work on a student.
  "agent_student.shortlist_add": "Added a university to a shortlist",
  "agent_student.shortlist_update": "Edited a shortlist entry",
  "agent_student.shortlist_remove": "Removed a university from a shortlist",
  // AGN-016 (DEC-SCOPE-051): task work on a student.
  "agent_student.task_add": "Added a task",
  "agent_student.task_update": "Edited a task",
  "agent_student.task_complete": "Completed a task",
  "agent_student.task_cancel": "Cancelled a task",
  "agent.student_link": "Linked a student account",
  "overseas.application.create": "Created an application",
  "overseas.application.update": "Edited an application",
  "overseas.application.advance": "Moved an application forward",
  "overseas.application.withdraw": "Withdrew an application",
  "document.upload": "Uploaded a document",
  "document.verify": "Verified a document",
};

export function activityLabel(action: string): string {
  return ACTIVITY_LABELS[action] ?? "Other activity";
}
