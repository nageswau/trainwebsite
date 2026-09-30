// AGN-002 (DEC-SCOPE-040): what the agency staff screens (AgentStaffPanel, AgentStaffRow, AgentStaffCreateForm) share.

export const STAFF_URL = "/api/v1/workflows/overseas/agent/team/staff";

export type StaffMember = { id: string; code: string; full_name: string; email: string; phone: string | null; status: "active" | "deactivated"; setup: "pending_setup" | "link_expired" | null };

// Browser QA-05/QA-06: how the staff screens word a failed request. A server error (5xx) carries no useful detail, so it says to
// retry; a dropped connection only promises a kept entry where something was typed (add / edit), not for a button action.
export function staffFailure(outcome: { message: string; status?: number }, keepsEntry: boolean): string {
  if (outcome.status === undefined) return keepsEntry ? outcome.message : "Couldn't reach the server. Check your connection and try again.";
  if (outcome.status >= 500) return "The server couldn't complete this. Please try again in a moment.";
  return outcome.message;
}
