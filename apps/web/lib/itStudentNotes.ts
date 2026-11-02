import type { Page } from "@/lib/apiErrors";

// itc-028 (DEC-SCOPE-351): notes on an IT student -- GET/POST /it/students/{id}/notes and PUT .../notes/{note}/visibility (staff: the
// itc-003 counselor, HR, the student's trainer, the IT Admin), and the student's shared ones on GET /it/me/updates. API_CONTRACT §12IW.

export type ItNoteVisibility = "internal" | "student";

export type ItStudentNote = {
  id: string;
  body: string;
  visibility: ItNoteVisibility;
  author_name: string;
  author_role: string;
  created_at: string;
  shared_at: string | null;
  can_change_visibility: boolean;
};

export type ItStudentNotes = Page<ItStudentNote> & { student: { id: string; full_name: string; student_code: string | null } };

export type ItStudentUpdate = { id: string; body: string; author_name: string; author_role: string; shared_at: string };

export const IT_NOTE_MAX = 4000;
export const PAGE_SIZE = 20;
export const MY_UPDATES_URL = "/api/v1/it/me/updates";
export const itStudentNotesUrl = (studentId: string) => `/api/v1/it/students/${encodeURIComponent(studentId)}/notes`;
export const itNoteVisibilityUrl = (studentId: string, noteId: string) => `${itStudentNotesUrl(studentId)}/${encodeURIComponent(noteId)}/visibility`;

export const IT_NOTE_AUTHOR_ROLE: Record<string, string> = { counselor: "Counselor", hr_team: "HR", trainer: "Trainer", it_admin: "IT Admin" };
export const authorRole = (role: string) => IT_NOTE_AUTHOR_ROLE[role] ?? role;
