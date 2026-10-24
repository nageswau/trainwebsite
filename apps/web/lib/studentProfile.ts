// ccrm-007 (DEC-SCOPE-249): the structured overseas student profile -- GET/PUT /counselor/students/{id}/profile (counselor, Overseas
// Admin), GET/PUT /overseas/me/profile (the student) and the agency's read-only GET (API_CONTRACT §12FB). A save replaces the whole
// profile, so the form always sends every field.

export type Qualification = {
  level: string;
  qualification_name: string | null;
  institution: string | null;
  board_university: string | null;
  year_completed: number | null;
  score_type: string | null;
  score: string | null;
  backlogs: number | null;
};

export type EnglishTest = {
  test_type: string;
  status: string | null;
  overall_score: string | null;
  test_date: string | null;
  valid_until: string | null;
  remarks: string | null;
  expired?: boolean;
};

export type StudentProfile = {
  exists: boolean;
  date_of_birth: string | null;
  nationality: string | null;
  city: string | null;
  state: string | null;
  passport_number?: string | null; // never in the agency's read (P3)
  passport_expiry?: string | null;
  work_experience_months: number | null;
  work_experience_details: string | null;
  preferred_countries: { id: string; name: string }[];
  preferred_course: string | null;
  preferred_level: string | null;
  preferred_intake: string | null;
  study_mode: string | null;
  budget_min: string | null;
  budget_max: string | null;
  budget_currency: string | null;
  qualifications: Qualification[];
  english_tests: EnglishTest[];
  updated_at: string | null;
  updated_by_name: string | null;
};

export type StudentProfileResponse = {
  student: { id: string; full_name: string; student_code: string | null };
  profile: StudentProfile;
};

export type CountryOption = { id: string; name: string };

export const MY_PROFILE_URL = "/api/v1/overseas/me/profile";
export const studentProfileUrl = (id: string) => `/api/v1/counselor/students/${encodeURIComponent(id)}/profile`;
export const agencyProfileUrl = (id: string) => `/api/v1/workflows/overseas/agent/crm/students/${encodeURIComponent(id)}/profile`;

export const MAX_QUALIFICATIONS = 10;
export const MAX_ENGLISH_TESTS = 5;
export const MAX_PREFERRED_COUNTRIES = 5;

export const QUALIFICATION_LEVELS: Record<string, string> = {
  class_10: "Class 10",
  class_12: "Class 12",
  diploma: "Diploma",
  bachelor: "Bachelor's degree",
  master: "Master's degree",
  phd: "PhD",
  other: "Other",
};
export const SCORE_TYPES: Record<string, string> = { percentage: "Percentage", cgpa: "CGPA (out of 10)" };
export const COURSE_LEVELS: Record<string, string> = { UG: "Undergraduate", PG: "Postgraduate", PhD: "PhD", Diploma: "Diploma", Foundation: "Foundation" };
export const STUDY_MODES: Record<string, string> = { full_time: "Full-time", part_time: "Part-time", online: "Online" };
export const CURRENCIES = ["INR", "USD", "GBP", "EUR", "CAD", "AUD", "NZD"];
export const ENGLISH_TESTS = ["IELTS", "TOEFL", "PTE", "Duolingo", "Other"];
export const TEST_STATUSES: Record<string, string> = { not_taken: "Not taken yet", booked: "Booked", taken: "Taken" };
// The server's ranges (schemas.ENGLISH_SCORE_RANGES); the inputs use them so most mistakes are caught before sending.
export const ENGLISH_SCORE_RANGES: Record<string, [number, number]> = { IELTS: [0, 9], TOEFL: [0, 120], PTE: [10, 90], Duolingo: [10, 160], Other: [0, 999] };

export const emptyQualification = (): Qualification => ({
  level: "bachelor", qualification_name: null, institution: null, board_university: null, year_completed: null, score_type: null, score: null, backlogs: null,
});
export const emptyEnglishTest = (): EnglishTest => ({ test_type: "IELTS", status: null, overall_score: null, test_date: null, valid_until: null, remarks: null });

const FIELD_LABELS: Record<string, string> = {
  date_of_birth: "Date of birth", nationality: "Nationality", city: "City", state: "State", passport_number: "Passport number",
  passport_expiry: "Passport expiry", work_experience_months: "Work experience (months)", work_experience_details: "Work experience details",
  preferred_country_ids: "Preferred countries", preferred_course: "Course or subject", preferred_level: "Study level", preferred_intake: "Intake",
  study_mode: "Study mode", budget_min: "Budget from", budget_max: "Budget to", budget_currency: "Budget currency",
  level: "Level", qualification_name: "Qualification", institution: "Institution", board_university: "Board or university",
  year_completed: "Year completed", score_type: "Score type", score: "Score", backlogs: "Backlogs", test_type: "Test", status: "Status",
  overall_score: "Overall score", test_date: "Test date", valid_until: "Valid until", remarks: "Remarks",
};

/** A 422 item's location in words -- "Qualification 2 · Score" -- so a message in a long form says where it is. */
export function fieldPlace(loc: unknown): string | null {
  if (!Array.isArray(loc)) return null;
  const parts = loc.filter((p) => p !== "body");
  const words: string[] = [];
  for (let i = 0; i < parts.length; i++) {
    const part = parts[i];
    if (part === "qualifications" || part === "english_tests") {
      const row = typeof parts[i + 1] === "number" ? ` ${Number(parts[i + 1]) + 1}` : "";
      words.push(`${part === "qualifications" ? "Qualification" : "English test"}${row}`);
      if (row) i++;
    } else if (typeof part === "string" && FIELD_LABELS[part]) words.push(FIELD_LABELS[part]);
  }
  return words.length ? words.join(" · ") : null;
}

/** The PUT body: every field, blanks as null (a save replaces the whole profile). */
export function toSaveBody(profile: StudentProfile) {
  const blank = (v: string | null | undefined) => (v === undefined || v === null || v.trim() === "" ? null : v.trim());
  const num = (v: number | string | null | undefined) => (v === null || v === undefined || String(v).trim() === "" ? null : Number(v));
  return {
    date_of_birth: blank(profile.date_of_birth),
    nationality: blank(profile.nationality),
    city: blank(profile.city),
    state: blank(profile.state),
    passport_number: blank(profile.passport_number),
    passport_expiry: blank(profile.passport_expiry),
    work_experience_months: num(profile.work_experience_months),
    work_experience_details: blank(profile.work_experience_details),
    preferred_country_ids: profile.preferred_countries.map((c) => c.id),
    preferred_course: blank(profile.preferred_course),
    preferred_level: blank(profile.preferred_level),
    preferred_intake: blank(profile.preferred_intake),
    study_mode: blank(profile.study_mode),
    budget_min: blank(profile.budget_min),
    budget_max: blank(profile.budget_max),
    budget_currency: blank(profile.budget_currency),
    qualifications: profile.qualifications.map((q) => ({
      level: q.level, qualification_name: blank(q.qualification_name), institution: blank(q.institution), board_university: blank(q.board_university),
      year_completed: num(q.year_completed), score_type: blank(q.score_type), score: blank(q.score), backlogs: num(q.backlogs),
    })),
    english_tests: profile.english_tests.map((t) => ({
      test_type: t.test_type, status: blank(t.status), overall_score: blank(t.overall_score), test_date: blank(t.test_date), valid_until: blank(t.valid_until), remarks: blank(t.remarks),
    })),
  };
}
