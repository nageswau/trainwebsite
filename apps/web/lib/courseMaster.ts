// upc-017 (DEC-SCOPE-146): the §16 course master -- types, value lists, words, URLs and the "Courses & Programs" menu's query helpers.
// The API is the gate: it leaves `commission` out of every course for the non-commission roles (U2) and refuses them setting it. Nothing
// here filters for security.
import type { Page } from "@/lib/apiErrors";
import { universityUrl } from "@/lib/universities";

export { CURRENCIES } from "@/lib/agentStudents"; // the project's currency list (models.COURSE_CURRENCIES)
export const LEVELS = ["UG", "PG", "PhD", "Diploma", "Foundation"] as const; // CO3: the master's levels
export const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"] as const; // CO7
export const MAX_SCORE: Record<string, number> = { IELTS: 9, TOEFL: 120, PTE: 90, Duolingo: 160, Other: 999.9 }; // CO8
export const ENGLISH_TESTS = Object.keys(MAX_SCORE);
export const COMMISSION_ROLES = new Set(["super_admin", "partnership_manager", "partnership_head"]); // U2: who may set it (the API decides)

export type CourseCommission = { percent: string | null; amount: string | null; currency: string | null };
export type Course = {
  id: string; university_id: string; title: string; level: string; category: string; duration: string; tuition_fee: string; intake: string;
  tuition_amount: string | null; tuition_currency: string | null; application_fee: string | null; application_fee_currency: string | null;
  intakes: string[]; entry_requirements: string | null; english_test: string | null; english_score: string | null;
  scholarships: { id: string; title: string; amount: string }[]; application_process: string | null; deadline: string | null; active: boolean;
  commission?: CourseCommission | null; // present for the commission roles only
  permissions: { can_edit: boolean };
};
export type CoursePage = Page<Course> & { can_edit: boolean };
export type CourseRow = Course & { university: { id: string; name: string; university_code: string; country: string } };
export type CourseOptions = { scholarships: { id: string; title: string; amount: string }[] };

export const COURSES_URL = "/api/v1/partnership/courses";
export const COURSES_PATH = "/partnership/courses";
export const coursesUrl = (universityId: string, courseId?: string) => universityUrl(universityId, `courses${courseId ? `/${courseId}` : ""}`);
export const courseOptionsUrl = (universityId: string) => universityUrl(universityId, "course-options");
export const courseImportUrl = (universityId: string) => universityUrl(universityId, "courses/import");
export const courseTemplateUrl = (universityId: string) => universityUrl(universityId, "courses/imports/template");

/** "GBP 18,000" / "GBP 75.50"; null when there is no amount. */
export function moneyText(amount: string | null, currency: string | null): string | null {
  if (amount === null || currency === null) return null;
  const n = Number(amount);
  const digits = Number.isInteger(n) ? 0 : 2;
  return `${currency} ${n.toLocaleString("en-GB", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
}

export function commissionText(c: CourseCommission | null | undefined): string {
  if (!c) return "Not recorded";
  return c.percent !== null ? `${Number(c.percent)}%` : (moneyText(c.amount, c.currency) ?? "Not recorded");
}

export function englishText(c: Pick<Course, "english_test" | "english_score">): string | null {
  if (!c.english_test) return null;
  return c.english_score ? `${c.english_test} ${Number(c.english_score)}` : c.english_test;
}

/** The form's own check of the English score (the API repeats it). */
export function scoreProblem(test: string, score: string): string | null {
  if (!score.trim()) return null;
  if (!test) return "Choose the English test the score is for.";
  const n = Number(score);
  if (!(n > 0)) return "The English score must be more than 0.";
  if (n > MAX_SCORE[test]) return `The ${test} score cannot be above ${MAX_SCORE[test]}.`;
  return null;
}

// The menu page's filters travel in the URL; only these keys are passed on to the API.
export const COURSE_FILTER_KEYS = ["q", "level", "status"] as const;
export type CourseFilters = Partial<Record<(typeof COURSE_FILTER_KEYS)[number] | "offset", string>>;

function filterParams(filters: CourseFilters): URLSearchParams {
  const query = new URLSearchParams();
  for (const key of COURSE_FILTER_KEYS) {
    const value = filters[key]?.trim();
    if (value) query.set(key, value);
  }
  return query;
}

export function courseListQuery(filters: CourseFilters, limit: number, offset: number): string {
  const query = filterParams(filters);
  query.set("limit", String(limit));
  query.set("offset", String(offset));
  return query.toString();
}

export function coursePageHref(filters: CourseFilters, offset: number): string {
  const query = filterParams(filters);
  if (offset > 0) query.set("offset", String(offset));
  const text = query.toString();
  return text ? `${COURSES_PATH}?${text}` : COURSES_PATH;
}
