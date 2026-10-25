// tel-004 (DEC-SCOPE-081, spec §2/§6): the EVID-019 §19 lead pipeline. Mirrors apps/api/app/lead_stages.py so the stage picker offers
// only moves the API will accept; the API stays the authority (it answers 422/403 for anything else).

export const OPEN_STAGES = [
  ["new", "New Lead"],
  ["assigned", "Assigned"],
  ["first_call_pending", "First Call Pending"],
  ["contacted", "Contacted"],
  ["qualified", "Qualified"],
  ["interested", "Interested"],
  ["follow_up", "Follow-up"],
  ["counselling_scheduled", "Counselling Scheduled"],
  ["counselling_completed", "Counselling Completed"],
  ["application_enrollment", "Application/Enrollment"],
  ["converted", "Converted"],
] as const;
export const CLOSED_STAGES = [
  ["not_interested", "Not Interested"],
  ["not_eligible", "Not Eligible"],
  ["wrong_number", "Invalid Contact"], // ccrm-006 D1: the spec's Invalid Contact -- relabelled, the key stays
  ["no_response", "No Response"],
  ["lost", "Lost"],
  ["duplicate", "Duplicate"], // ccrm-006 D2/D3
] as const;

export const STAGES: readonly (readonly [string, string])[] = [...OPEN_STAGES, ...CLOSED_STAGES];
const LABELS: Record<string, string> = Object.fromEntries(STAGES);
const ORDER: string[] = OPEN_STAGES.map(([key]) => key);
const MANUAL = ["qualified", "interested", "follow_up"];
const CLOSED: string[] = CLOSED_STAGES.map(([key]) => key);
export const REOPEN_TO = "follow_up";

/** A key no longer in the catalogue (history after a future change) is shown as stored. */
export const stageLabel = (stage: string) => LABELS[stage] ?? stage;
export const isClosed = (stage: string) => CLOSED.includes(stage);

/** The stages a person may move a lead to from `current` (spec §4 D2/D3). A closed lead only reopens to Follow-up, and only for a
 *  manager or admin (`canReopen`). Manual moves stop at Application/Enrollment; nothing moves a Converted lead. */
export function personTargets(current: string, canReopen: boolean): string[] {
  if (isClosed(current)) return canReopen ? [REOPEN_TO] : [];
  if (current === "converted") return [];
  const beforeCounselor = ORDER.indexOf(current) < ORDER.indexOf("application_enrollment");
  return [...(beforeCounselor ? MANUAL : []), ...CLOSED].filter((stage) => stage !== current);
}

// ccrm-003 (DEC-SCOPE-243, CC8 / A1): mirrors COUNSELOR_MANUAL / COUNSELOR_CLOSED in apps/api/app/lead_stages.py.
const COUNSELOR_MANUAL = ["qualified", "follow_up", "counselling_scheduled", "counselling_completed"];
const COUNSELOR_CLOSED = ["not_interested", "not_eligible", "lost"];

/** The counselor's moves from `current`: the CC8 open stages until the student link, the three closed outcomes; never a reopen. */
export function counselorTargets(current: string): string[] {
  if (isClosed(current) || current === "converted") return [];
  const beforeLink = ORDER.indexOf(current) < ORDER.indexOf("application_enrollment");
  return [...(beforeLink ? COUNSELOR_MANUAL : []), ...COUNSELOR_CLOSED].filter((stage) => stage !== current);
}

// ccrm-006 (DEC-SCOPE-262, D3/D4): Lost / Not Interested take a reason from the list, Duplicate the surviving lead's Lead ID.
const LOSS_STAGES = ["lost", "not_interested"];
export const isLoss = (stage: string) => LOSS_STAGES.includes(stage);
export type Closure = { duplicate_of?: string; lost_reason_id?: string; lost_to?: string };
/** How a lead closed, as every lead read returns it (optional: older fixtures and callers predate ccrm-006). */
export type LeadClosureFields = {
  duplicate_of?: { id?: string; lead_code: string } | null; lost_reason?: { id: string; name: string } | null; lost_to?: string | null;
};
export const LOST_REASONS_URL = "/api/v1/telecaller/lost-reasons";
export type LostReason = { id: string; name: string; active: boolean; sort_order: number };

/** Closed outcomes and reopening need a reason (D1); ccrm-006 D5: not when the close carries its structured reason instead. */
export const needsReason = (current: string, target: string) =>
  isClosed(current) || (isClosed(target) && !isLoss(target) && target !== "duplicate");
