// ENH-025 (DEC-SCOPE-027): the shared shape and helpers for a School student record, so the roster, the
// student pages and the counsellor card read one definition instead of per-component copies.

export type SchoolStudent = {
  id: string;
  student_code: string;
  full_name: string;
  date_of_birth: string | null;
  grade_or_class: string | null;
  academic_year_id: string | null;
  grade_level: number | null;
  assigned_teacher_user_id: string | null;
  pending_parent_email: string | null;
  section: string | null;
  roll_number: string | null;
  gender: string | null;
  student_mobile: string | null;
  city: string | null;
  subjects: string[] | null;
  career_interests: string[] | null;
  global_education_interest: boolean | null;
  preferred_countries: string[] | null;
  preferred_courses: string[] | null;
  has_photo: boolean;
};

export const GENDER_OPTIONS = [
  { value: "female", label: "Female" },
  { value: "male", label: "Male" },
  { value: "other", label: "Other" },
  { value: "prefer_not_to_say", label: "Prefer not to say" },
];

export const GENDER_LABEL: Record<string, string> = Object.fromEntries(GENDER_OPTIONS.map((o) => [o.value, o.label]));

const TEXT_FIELDS = ["section", "roll_number", "gender", "student_mobile", "city"] as const;
export const MASTER_LIST_FIELDS = ["subjects", "career_interests", "preferred_countries", "preferred_courses"] as const;

export function listText(value: string[] | null | undefined): string {
  return value ? value.join(", ") : "";
}

export function splitList(raw: FormDataEntryValue | null): string[] {
  return String(raw ?? "").split(",").map((s) => s.trim()).filter(Boolean);
}

/** A "yes"/"no"/"" select value as the API's nullable boolean. */
export function interestValue(raw: FormDataEntryValue | null): boolean | null {
  const value = String(raw ?? "");
  return value === "" ? null : value === "yes";
}

/** create: empty fields are omitted; edit: empty fields are sent as null so the server clears them. */
export function toMasterPayload(form: FormData, mode: "create" | "edit"): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  const put = (key: string, value: unknown, empty: boolean) => {
    if (!empty) out[key] = value;
    else if (mode === "edit") out[key] = null;
  };
  for (const key of TEXT_FIELDS) {
    const raw = String(form.get(key) ?? "").trim();
    put(key, raw, raw === "");
  }
  for (const key of MASTER_LIST_FIELDS) {
    const items = splitList(form.get(key));
    put(key, items, items.length === 0);
  }
  const interest = interestValue(form.get("global_education_interest"));
  put("global_education_interest", interest, interest === null);
  return out;
}

// QA2-05/06: the API names fields ("roll_number '12' is already used…"); users see the labels they typed into, and the
// form uses the field to mark and focus the input the message is about.
const FIELD_LABELS: Record<string, string> = {
  full_name: "Full name",
  date_of_birth: "Date of birth",
  grade_or_class: "Grade/Class",
  grade_level: "Grade level",
  section: "Section",
  roll_number: "Roll number",
  gender: "Gender",
  student_mobile: "Student mobile",
  city: "City",
  subjects: "Subjects",
  career_interests: "Career interests",
  global_education_interest: "Interested in studying abroad",
  preferred_countries: "Preferred countries",
  preferred_courses: "Preferred courses",
  parent_email: "Parent's email",
  parent_name: "Parent's name",
  assigned_teacher_user_id: "Assigned teacher",
  assigned_teacher_email: "Assigned teacher",
  photo: "Photo",
};
const LIST_ITEM_LABELS: Record<string, string> = {
  subjects: "Each subject",
  career_interests: "Each career interest",
  preferred_countries: "Each preferred country",
  preferred_courses: "Each preferred course",
};
// Longest first, so "preferred_countries" never matches a shorter key that happens to prefix it.
const FIELD_KEYS = Object.keys(FIELD_LABELS).sort((a, b) => b.length - a.length);

/** The API field a validation message is about, or null. */
export function fieldFromMessage(message: string): string | null {
  return FIELD_KEYS.find((key) => message.startsWith(`${key} `)) ?? null;
}

/** A server validation message in the words the user sees on the form. Unrecognised messages pass through unchanged. */
export function friendlyMessage(message: string): string {
  const roll = /^roll_number '(.*)' is already used/.exec(message);
  if (roll) return message.replace(`roll_number '${roll[1]}'`, `Roll number ${roll[1]}`);
  const key = fieldFromMessage(message);
  if (!key) return message;
  const rest = message.slice(key.length + 1);
  if (LIST_ITEM_LABELS[key] && rest.startsWith("items ")) return `${LIST_ITEM_LABELS[key]} ${rest.slice("items ".length)}`;
  return `${FIELD_LABELS[key]} ${rest}`;
}

export function detailMessage(detail: unknown, fallback = "Something went wrong."): string {
  if (typeof detail === "string") return friendlyMessage(detail);
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return fallback;
}

export const ROSTER_COLUMNS: { name: string; required: boolean; format: string; example: string }[] = [
  { name: "full_name", required: true, format: "Text", example: "Jane Doe" },
  { name: "date_of_birth", required: false, format: "YYYY-MM-DD", example: "2015-04-12" },
  { name: "grade_or_class", required: false, format: "Text label, up to 60 characters", example: "Grade 5-A" },
  { name: "assigned_teacher_email", required: false, format: "Email of an existing Teacher at your school", example: "teacher@school.edu" },
  { name: "parent_name", required: false, format: "Text (used only when inviting a new parent)", example: "Jane's Parent" },
  { name: "parent_email", required: false, format: "Email; links or invites the parent", example: "parent@example.com" },
  { name: "grade_level", required: false, format: "Whole number 1-12", example: "5" },
  { name: "section", required: false, format: "Up to 20 characters", example: "A" },
  { name: "roll_number", required: false, format: "Up to 20 characters; unique within grade + section + year", example: "12" },
  { name: "gender", required: false, format: "female, male, other or prefer_not_to_say", example: "female" },
  { name: "student_mobile", required: false, format: "7-20 digits, spaces, + - ( )", example: "+91 98765 43210" },
  { name: "city", required: false, format: "Up to 120 characters", example: "Pune" },
  { name: "subjects", required: false, format: "List separated by ;", example: "Maths;Science" },
  { name: "career_interests", required: false, format: "List separated by ;", example: "Engineering" },
  { name: "global_education_interest", required: false, format: "yes or no", example: "yes" },
  { name: "preferred_countries", required: false, format: "List separated by ;", example: "Germany;Canada" },
  { name: "preferred_courses", required: false, format: "List separated by ;", example: "Mechanical Engineering" },
];
