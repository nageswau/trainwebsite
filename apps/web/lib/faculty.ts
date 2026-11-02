// itc-019 (DEC-SCOPE-347): trainer profiles and the student faculty view. API_CONTRACT.md §12IS.

export const OWN_PROFILE_API = "/api/v1/it/trainer/profile";
export const MY_FACULTY_API = "/api/v1/it/student/faculty";
export const trainerProfileApi = (trainerId: string) => `/api/v1/it/trainers/${trainerId}/profile`;

export type ContactRoute = "in_app" | "email" | "phone";

/** The fields a PUT replaces (TrainerProfileIn). */
export type ProfileFields = {
  designation: string | null;
  expertise: string[];
  bio: string | null;
  office_hours: string | null;
  contact_route: ContactRoute;
  show_email: boolean;
  show_phone: boolean;
  show_photo: boolean;
  show_bio: boolean;
  show_office_hours: boolean;
};

/** The editor's view (trainer or IT Admin): every field, plus the account email/phone the trainer may show. */
export type OwnProfile = ProfileFields & { trainer_id: string; name: string; account_email: string | null; account_phone: string | null; photo_url: string | null };

/** What a student receives. Hidden fields are absent, never null (AC1). */
export type FacultyView = {
  trainer_id: string;
  name: string;
  designation: string | null;
  expertise: string[];
  contact_route: ContactRoute;
  bio?: string;
  office_hours?: string;
  photo_url?: string;
  email?: string;
  phone?: string;
};

export type MyFacultyItem = { batch_id: string; batch: string; program: string; faculty: FacultyView | null };

export const FIELD_KEYS = ["designation", "expertise", "bio", "office_hours", "contact_route", "show_email", "show_phone", "show_photo", "show_bio", "show_office_hours"] as const;

export function profileBody(profile: ProfileFields): ProfileFields {
  return Object.fromEntries(FIELD_KEYS.map((key) => [key, profile[key]])) as ProfileFields;
}

/** Comma- or newline-separated tags, trimmed, blanks and case-insensitive repeats dropped (the API does the same). */
export function parseExpertise(text: string): string[] {
  const seen = new Map<string, string>();
  for (const tag of text.split(/[,\n]/).map((t) => t.trim())) if (tag && !seen.has(tag.toLowerCase())) seen.set(tag.toLowerCase(), tag);
  return [...seen.values()];
}

/** The editor's "What students see" preview -- the same rules as the API's `public_view`. */
export function studentPreview(p: OwnProfile): FacultyView {
  const view: FacultyView = { trainer_id: p.trainer_id, name: p.name, designation: p.designation || null, expertise: p.expertise, contact_route: "in_app" };
  if (p.show_bio && p.bio) view.bio = p.bio;
  if (p.show_office_hours && p.office_hours) view.office_hours = p.office_hours;
  if (p.show_photo && p.photo_url) view.photo_url = p.photo_url;
  if (p.show_email && p.account_email) view.email = p.account_email;
  if (p.show_phone && p.account_phone) view.phone = p.account_phone;
  if (p.contact_route !== "in_app" && view[p.contact_route]) view.contact_route = p.contact_route;
  return view;
}
