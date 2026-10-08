// rec-002 (DEC-SCOPE-117): the recruiter managed lists and campaigns -- the tabs, endpoints and the shared picker source later rec items
// read (rec-003's company form, rec-009's candidate form). Labels are display only -- the API decides who may write.
import { formOptional, formText } from "@/lib/telecaller";
import { readAll } from "@/lib/telecallerCatalogue";

export type CatalogueValue = { id: string; name: string; active: boolean; sort_order: number };
export type RecCampaign = { id: string; name: string; lead_source: { id: string; name: string; active: boolean }; start_date: string; end_date: string | null; active: boolean };

export const CATALOGUE_URL = "/api/v1/recruiter/catalogue";
export const CAMPAIGNS_URL = `${CATALOGUE_URL}/campaigns`;
export const CATALOGUE_PATH = "/recruiter/manager/catalogue";

type Tab = { label: string; noun: string; intro: string };
// The six simple lists, in the order EVID-018 introduces them (§2, §9, §3, §3, §4, §6/§26); campaigns last (they hang off a lead
// source). The intros speak to the manager, so they carry no section references (QA-01).
export const VALUE_TABS = {
  "lead-sources": { label: "Lead sources", noun: "lead source", intro: "Where a company lead came from." },
  "candidate-sources": { label: "Candidate sources", noun: "candidate source", intro: "Where a candidate came from." },
  industries: { label: "Industries", noun: "industry", intro: "A company's industry. Add the industries you work with." },
  "company-sizes": { label: "Company sizes", noun: "company size", intro: "A company's size band, by number of employees." },
  "contact-roles": { label: "Contact roles", noun: "contact role", intro: "The role of a contact at a company." },
  "job-categories": { label: "Job categories", noun: "job category", intro: "A requirement's job category, also used in reports." },
} satisfies Record<string, Tab>;
export type ValueKind = keyof typeof VALUE_TABS;
export const TABS: Record<ValueKind | "campaigns", Tab> = {
  ...VALUE_TABS,
  campaigns: { label: "Campaigns", noun: "campaign", intro: "Each campaign names its lead source, for example LinkedIn → Q4 IT hiring push." },
};
export const isTab = (kind: string): kind is ValueKind | "campaigns" => Object.hasOwn(TABS, kind);

/** A picker's source: every active value of one list, page after page, in list order (the API orders them). */
export const activeValues = (kind: ValueKind, signal?: AbortSignal) => readAll<CatalogueValue>(`${CATALOGUE_URL}/${kind}`, signal);

/** The campaign create and edit forms' body: trimmed text, an empty end date sent as null. */
export function campaignBody(form: FormData) {
  return {
    name: formText(form, "name"), lead_source_id: formText(form, "lead_source_id"),
    start_date: formText(form, "start_date"), end_date: formOptional(form, "end_date"),
  };
}
