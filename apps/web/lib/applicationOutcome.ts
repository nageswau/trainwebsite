// ccrm-015 (DEC-SCOPE-244): mirrors apps/api/app/application_outcome.py -- an application's exception outcome, independent of its stage.
// ccrm-027 (DEC-SCOPE-259, E6): non_arrival / cancelled -- post-offer and terminal, like offer_declined.
export const SETTABLE_OUTCOMES = ["rejected", "withdrawn", "deferred", "on_hold", "offer_declined", "non_arrival", "cancelled"] as const;
export type SettableOutcome = (typeof SETTABLE_OUTCOMES)[number];
export const TERMINAL_OUTCOMES = ["rejected", "withdrawn", "offer_declined", "visa_refused", "non_arrival", "cancelled"];
const POST_OFFER: string[] = ["offer_declined", "non_arrival", "cancelled"];
export const REQUESTERS = ["student", "counselor", "agent", "university"] as const;
const OFFER_STAGES = ["offer", "visa_documentation", "status_tracking"];

export const outcomeLabel = (value: string) => value.replaceAll("_", " ").replace(/^\w/, (c) => c.toUpperCase());

export const isTerminal = (outcome: string | null | undefined) => !!outcome && TERMINAL_OUTCOMES.includes(outcome);

/** The outcomes a counselor can record now: none once closed or enrolled; the post-offer ones only from the offer stage on. */
export function outcomeChoices(stage: string, outcome: string | null | undefined): SettableOutcome[] {
  if (stage === "withdrawn" || stage === "enrolled" || isTerminal(outcome)) return [];
  return SETTABLE_OUTCOMES.filter((o) => !POST_OFFER.includes(o) || OFFER_STAGES.includes(stage));
}

export type OutcomeDetail = {
  outcome: string;
  label: string;
  outcome_date: string | null;
  next_steps: string | null;
  new_intake: string | null;
  terminal: boolean;
  reason?: string | null;
  requested_by?: string | null;
  review_date?: string | null;
  hold_owner?: string | null;
  another_offer_preferred?: boolean | null;
};
