import type { OwnerRef } from "@/lib/recruiterCandidates";

// hrc-025 (DEC-SCOPE-402): the New Website Registrations workspace -- the API shape and the "Show" filter (N3), in the API's order.
export const WEBSITE_REGISTRATIONS_URL = "/api/v1/recruiter/candidates/website-registrations";
export const WEBSITE_REGISTRATIONS_PATH = "/recruiter/website-registrations";

export const VIEWS = [
  { key: "unassigned", label: "Unassigned" },
  { key: "new", label: "New" },
  { key: "contacted", label: "Contacted" },
  { key: "screened", label: "Screened" },
  { key: "active", label: "Active" },
  { key: "inactive", label: "Inactive" },
  { key: "duplicate_review", label: "Duplicate review" },
] as const;
export const VIEW_KEYS = VIEWS.map((v) => v.key);

export const CONVERSION_LABEL = { registered: "Registered", applied: "Applied", placed: "Placed" } as const;

export type WebsiteRegistration = {
  id: string;
  candidate_code: string;
  name: string;
  registered_at: string;
  location: string | null;
  skills: string[];
  skill_count: number;
  completeness: number;
  owner: OwnerRef | null;
  engagement: { key: string; label: string } | null;
  first_contact_at: string | null;
  next_follow_up_at: string | null;
  conversion: keyof typeof CONVERSION_LABEL;
  contact_sla: "met" | "pending" | "breached";
  duplicate_review: boolean;
  can_open: boolean;
};
