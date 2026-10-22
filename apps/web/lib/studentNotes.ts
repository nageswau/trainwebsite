import type { Page } from "@/lib/apiErrors";

// ccrm-010 (DEC-SCOPE-241): internal notes on an overseas student -- GET/POST /counselor/students/{id}/notes (API_CONTRACT §12ET).

export type StudentNote = {
  id: string;
  body: string;
  author_name: string;
  author_role: string;
  application: { id: string; label: string } | null;
  created_at: string;
};

export type StudentNotes = Page<StudentNote> & {
  student: { id: string; full_name: string; student_code: string | null };
  applications: { id: string; label: string }[];
};

export const NOTE_MAX = 4000;

export const studentNotesUrl = (studentId: string) => `/api/v1/counselor/students/${encodeURIComponent(studentId)}/notes`;

export const AUTHOR_ROLE: Record<string, string> = { counselor: "Counselor", overseas_admin: "Overseas Admin" };
