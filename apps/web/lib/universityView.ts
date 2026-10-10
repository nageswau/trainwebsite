import type { Ranking } from "@/lib/universities";

// upc-030 (DEC-SCOPE-161): the role-sliced University 360 view. The API decides the slice; a section it leaves out is absent.
export type ViewSlice = "counselor" | "overseas_admin" | "bdm" | "university_rep";
export type ViewProfile = {
  id: string;
  university_code: string;
  name: string;
  institution_type: string;
  ownership_type: string | null;
  country: { name: string; iso2: string | null; region: string | null };
  state_region: string | null;
  city: string;
  website: string | null;
  overview: string;
  eligibility: string;
  course_levels: string[];
  popular_programs: string[];
  rankings: Ranking[];
};
export type ViewContact = {
  id: string;
  name: string;
  designation: string | null;
  department: string | null;
  role: { code: string; label: string } | null;
  email: string | null;
  phone: string | null;
  whatsapp: string | null;
  linkedin: string | null;
  preferred_channel: string | null;
  is_primary: boolean;
};
export type ViewCourse = {
  id: string;
  title: string;
  level: string;
  category: string;
  duration: string;
  tuition_fee: string;
  tuition_amount: string | null;
  tuition_currency: string | null;
  application_fee: string | null;
  application_fee_currency: string | null;
  intakes: string[];
  intake: string;
  entry_requirements: string | null;
  english_test: string | null;
  english_score: string | null;
  scholarships: { id: string; title: string; amount: string }[];
  application_process: string | null;
  deadline: string | null;
};
export type ViewDocument = { id: string; kind: string; title: string; current_version: number; updated_at: string };
export type ViewApplication = { id: string; reference: string | null; student_name: string | null; intake: string; status: string; next_action: string | null; updated_at: string };
export type UniversityView = {
  slice: ViewSlice;
  university: ViewProfile;
  partnership?: { stage: string; stage_label: string; lost: boolean };
  manager?: { full_name: string; email: string } | null;
  contacts?: ViewContact[];
  courses?: ViewCourse[];
  documents?: ViewDocument[];
  applications?: ViewApplication[];
};

export const universityViewUrl = (id: string) => `/api/v1/universities/${id}/view`;
export const viewDocumentFileUrl = (universityId: string, documentId: string) => `${universityViewUrl(universityId)}/documents/${documentId}/file`;
export const COUNSELOR_UNIVERSITIES_PATH = "/overseas/counselor/universities";
export const counselorUniversityPath = (id: string) => `${COUNSELOR_UNIVERSITIES_PATH}/${id}`;
export const bdmUniversityPath = (id: string) => `/bdm/universities/${id}`;
export const VIEW_REFUSED = "University view access required"; // the API's refusal (services/university_view.py REFUSED)
export const NOT_LINKED = "Your account is not linked to a university yet. Contact EduSphere Overseas Admin.";

export const money = (amount: string | null, currency: string | null) => (amount ? `${currency ?? ""} ${amount}`.trim() : null);

export function englishText(c: Pick<ViewCourse, "english_test" | "english_score">): string | null {
  if (!c.english_test) return null;
  return c.english_score ? `${c.english_test} ${c.english_score}` : c.english_test;
}
