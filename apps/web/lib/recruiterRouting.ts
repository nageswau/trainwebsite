// hrc-024 (DEC-SCOPE-393): candidate routing -- the placement manager's settings and rules for candidates the website creates.
import type { OwnerRef } from "@/lib/recruiterCandidates";

export type RoutingKind = "source" | "skill_category" | "location";
export type RoutingStrategy = "round_robin" | "least_workload";
export type RoutingRule = { id: string; kind: RoutingKind; value_id: string | null; value_label: string; recruiter: OwnerRef; created_at: string };
export type Routing = { default_recruiter: OwnerRef | null; strategy: RoutingStrategy; rules: RoutingRule[]; can_edit: boolean };

export const ROUTING_URL = "/api/v1/recruiter/candidate-routing";
export const ROUTING_PATH = "/recruiter/manager/routing";
export const UNASSIGNED_QUEUE_PATH = "/recruiter/candidates?owner=unassigned";
export const SOURCES_URL = "/api/v1/recruiter/catalogue/candidate-sources?active=true&limit=100";
export const CATEGORIES_URL = "/api/v1/recruiter/skill-categories?active=true&limit=100";

/** R1: the routing order -- the rules table lists them in this order. */
export const KINDS: { key: RoutingKind; label: string; help: string }[] = [
  { key: "source", label: "Candidate source", help: "Where the candidate came from, such as Website." },
  { key: "skill_category", label: "Skill category", help: "A category of any of the candidate's skills." },
  { key: "location", label: "Location", help: "The candidate's city (or location), matched exactly, ignoring capitals." },
];
export const KIND_LABEL = Object.fromEntries(KINDS.map((k) => [k.key, k.label])) as Record<RoutingKind, string>;
export const STRATEGIES: { key: RoutingStrategy; label: string; help: string }[] = [
  { key: "round_robin", label: "Round robin", help: "Recruiters on the same rule take turns." },
  { key: "least_workload", label: "Least workload", help: "The recruiter on the rule with the fewest open candidates; ties take turns." },
];
