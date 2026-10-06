// tel-004 (DEC-SCOPE-078, spec §2/§6): the EVID-019 §19 lead pipeline. Mirrors apps/api/app/lead_stages.py so the stage picker offers
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
  ["wrong_number", "Wrong Number"],
  ["no_response", "No Response"],
  ["lost", "Lost"],
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

/** Closed outcomes and reopening need a reason (D1). */
export const needsReason = (current: string, target: string) => isClosed(target) || isClosed(current);
