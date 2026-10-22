// ccrm-014 (DEC-SCOPE-238): mirrors apps/api/app/application_sub_status.py -- an application's sub-status under its stage.
const STAGES = ["enquiry", "eligibility_evaluation", "university_selection", "offer", "visa_documentation", "status_tracking", "enrolled"];

export const SUB_STATUSES: Record<string, string[]> = {
  university_selection: ["application_created", "documents_pending", "ready_for_submission", "submitted", "under_review"],
  offer: ["conditional_offer", "unconditional_offer", "offer_accepted"],
  visa_documentation: ["visa_preparation", "visa_applied"],
  status_tracking: ["visa_decision_pending", "visa_approved"],
  enrolled: ["enrolled"],
};

export const subStatusLabel = (value: string) => value.replaceAll("_", " ").replace(/^\w/, (c) => c.toUpperCase());

export type SubStatusGroup = { stage: string; options: string[] };

/** The choices from the current stage on (forward only), grouped by stage, without the one already set. `maxStage` caps the list
 * (agency: status tracking; a counselor on an agency application: before enrolled). A legacy stage counts as before the first. */
export function subStatusChoices(stage: string, current: string | null | undefined, maxStage = "enrolled"): SubStatusGroup[] {
  const from = Math.max(STAGES.indexOf(stage), 0);
  const to = STAGES.indexOf(maxStage);
  return STAGES.slice(from, to + 1)
    .map((s) => ({ stage: s, options: (SUB_STATUSES[s] ?? []).filter((o) => o !== current) }))
    .filter((group) => group.options.length > 0);
}
