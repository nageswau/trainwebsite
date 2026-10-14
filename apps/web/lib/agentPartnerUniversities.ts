import type { AgentCommission } from "@/lib/agentCommission";

// dtu-001: the published catalogue as an agent sees it. `agent_commission` is sent to a Master only (the server is the gate).
export const PARTNERS_URL = "/api/v1/workflows/overseas/agent/crm/partner-universities";
export const PARTNERS_PAGE_SIZE = 20;

export type PartnerUniversity = {
  id: string;
  slug: string;
  name: string;
  logo_url: string | null;
  city: string | null;
  campuses: string[];
  country: { id: string; name: string; iso2: string | null };
  course_count: number;
  agent_commission?: AgentCommission | null;
};
export type PartnerCourse = {
  id: string;
  title: string;
  level: string | null;
  category: string | null;
  duration: string | null;
  campus: string | null;
  fee_text: string | null;
  intake_text: string | null;
  tuition_fee: string | number | null;
  intake: string | null;
};
export type PartnerUniversityDetail = PartnerUniversity & {
  website: string | null;
  overview: string | null;
  fee_structure: string | null;
  deadlines: string[];
  scholarships: string[];
  courses: PartnerCourse[];
};
export type PartnerPage = { items: PartnerUniversity[]; total: number };

export const isPartnerPage = (d: unknown): d is PartnerPage => !!d && Array.isArray((d as PartnerPage).items) && typeof (d as PartnerPage).total === "number";
export const isPartnerDetail = (d: unknown): d is { university: PartnerUniversityDetail } => !!d && typeof (d as { university?: { id?: unknown } }).university?.id === "string";
export const safeWebsite = (url: string | null | undefined) => (url && /^https?:\/\//i.test(url) ? url : null);
