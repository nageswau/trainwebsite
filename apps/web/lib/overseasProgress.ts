// nehn-033 (DEC-SCOPE-332): the overseas student's Progress page -- GET /overseas/me/progress (API_CONTRACT.md §12ID). The step
// labels arrive ready to show (app/overseas_progress.py); only the state words and glyphs live here.

export const MY_PROGRESS_URL = "/api/v1/overseas/me/progress";

export type ProgressState = "done" | "current" | "upcoming" | "not_reached" | "stopped";
export type ProgressStep = { key: string; label: string; state: ProgressState };
export type ProgressApplication = {
  id: string;
  application_code: string | null;
  university: string;
  intake: string | null;
  current: { key: string; label: string };
  closed: boolean;
  note: string | null;
  steps: ProgressStep[];
};
export type MissingDocument = {
  name: string;
  source: string;
  application_code: string | null;
  university: string | null;
  status_label: string;
  due_date: string | null;
  overdue: boolean;
  upload_url: string;
};
export type NextAction = { text: string; href: string | null };
export type Progress = { applications: ProgressApplication[]; missing_documents: MissingDocument[]; next_actions: NextAction[] };

export const STATE_LABELS: Record<ProgressState, string> = { done: "Done", current: "Current", upcoming: "Not yet", not_reached: "Not reached", stopped: "Stopped" };
// jny-* classes (AGN-015): done reads green, stopped red -- always beside the word, never colour alone.
export const STATE_CLASS: Record<ProgressState, string> = { done: "done", current: "current", upcoming: "not_started", not_reached: "not_started", stopped: "refused" };
export const GLYPH: Record<ProgressState, string> = { done: "✓", current: "•", upcoming: "–", not_reached: "–", stopped: "✕" };
