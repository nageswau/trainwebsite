// pob-020 (DEC-SCOPE-412): the question bank, a requirement's versioned screening form, sessions and comparison. The API decides every
// rule (S6-S13); these types and helpers only shape what is shown and sent.
export type Option = { key: string; label: string };
export type Catalogue = { categories: Option[]; formats: Option[] };

export type QuestionFields = {
  category: string; text: string; format: string; choices: string[] | null; evaluation_criteria: string | null; expected_answer: string | null;
};
export type BankQuestion = QuestionFields & { id: string; category_label: string; format_label: string; active: boolean };
export type FormQuestion = QuestionFields & { id: string; question_id: string | null; position: number; category_label: string; format_label: string; is_knockout: boolean };
export type ScreeningForm = {
  id: string; name: string; version: number; knockout_status: "none" | "pending" | "approved"; knockout_status_label: string;
  knockout_approved_by: { id: string; full_name: string } | null; knockout_approved_at: string | null; questions: FormQuestion[];
};
export type FormRead = Catalogue & { form: ScreeningForm | null; templates: { id: string; name: string; is_default: boolean }[]; can_edit: boolean; can_approve: boolean };
export type Template = { id: string; name: string; is_default: boolean; version: number; archived: boolean; questions: FormQuestion[] };

export type Scorecard = { total: number; max: number; percent: number };
export type SessionAnswer = { question_id: string; question: string; category: string; format: string; is_knockout: boolean; answer: string | null; answer_hidden?: boolean; score: number | null };
export type Session = {
  id: string; kind: "form" | "legacy"; form_version: number | null; screened_by: { id: string; full_name: string }; created_at: string; notes: string | null;
  recommendation: string; recommendation_label: string; knockout_triggered: boolean; knockout_overridden: boolean; override_reason: string | null;
  answers: SessionAnswer[]; scorecard: Scorecard | null; checklist: (Record<string, unknown> & { result_label: string }) | null;
};
export type SessionsRead = { form: ScreeningForm | null; sessions: Session[]; can_run: boolean; sees_compensation: boolean; recommendations: Option[] };

export type ComparisonRow = {
  application_id: string; candidate: { id: string; code: string; name: string }; status_label: string; session_id: string; created_at: string; recommendation: string;
  recommendation_label: string; knockout_triggered: boolean; knockout_overridden: boolean; scorecard: Scorecard | null;
  answers: Record<string, { answer: string | null; answer_hidden?: boolean; score: number | null }>;
};
export type Comparison = { version: number | null; versions: number[]; questions: FormQuestion[]; rows: ComparisonRow[]; truncated: boolean };

export const QUESTIONS_URL = "/api/v1/recruiter/screening/questions";
export const TEMPLATES_URL = "/api/v1/recruiter/screening/templates";
export const formUrl = (requirementId: string, suffix = "") => `/api/v1/recruiter/requirements/${encodeURIComponent(requirementId)}/screening-form${suffix}`;
export const comparisonUrl = (requirementId: string, version?: number) =>
  `/api/v1/recruiter/requirements/${encodeURIComponent(requirementId)}/screening-comparison${version ? `?version=${version}` : ""}`;
export const sessionsUrl = (applicationId: string) => `/api/v1/recruiter/applications/${encodeURIComponent(applicationId)}/screening-sessions`;

export const COMPENSATION = "compensation";
export const SCORES = [0, 1, 2, 3, 4, 5];
export const RATINGS = ["1", "2", "3", "4", "5"];
export const LIMITS = { text: 500, criteria: 1000, expected: 500, answer: 2000, notes: 2000, reason: 500, name: 120, questions: 20 };
export const yesNoLabel = (value: string | null) => (value === "yes" ? "Yes" : value === "no" ? "No" : value ?? "—");
export const scoreText = (card: Scorecard | null) => (card ? `${card.total} / ${card.max} (${card.percent}%)` : "Not scored");

/** S7/S8: which knock-outs count on this form, and whether these answers fail one. The API decides again on save. */
export function failedKnockouts(form: ScreeningForm, answers: Record<string, string>): FormQuestion[] {
  if (form.knockout_status !== "approved") return [];
  return form.questions.filter((q) => q.is_knockout && answers[q.id] && answers[q.id] !== q.expected_answer);
}

// The form builder's own row: `choices` is one line per choice until sent.
export type QuestionDraft = {
  key: string; question_id: string | null; category: string; text: string; format: string; choices: string; evaluation_criteria: string; expected_answer: string; is_knockout: boolean;
};
let nextKey = 0;
const key = () => `q${++nextKey}`;
export const blankDraft = (): QuestionDraft => ({ key: key(), question_id: null, category: "technical", text: "", format: "text", choices: "", evaluation_criteria: "", expected_answer: "", is_knockout: false });
// `bank`: picked just now, so it goes by id. A form's existing row goes as its own text: the bank may have changed or archived it since.
export const draftOf = (q: QuestionFields & { id?: string; is_knockout?: boolean }, bank = false): QuestionDraft => ({
  key: key(), question_id: bank ? q.id ?? null : null, category: q.category, text: q.text, format: q.format, choices: (q.choices ?? []).join("\n"),
  evaluation_criteria: q.evaluation_criteria ?? "", expected_answer: q.expected_answer ?? "", is_knockout: q.is_knockout ?? false,
});
export const choiceList = (value: string) => value.split("\n").map((c) => c.trim()).filter(Boolean);

export const questionBody = (d: QuestionDraft) => ({
  category: d.category, text: d.text.trim(), format: d.format, choices: d.format === "choice" ? choiceList(d.choices) : null,
  evaluation_criteria: d.evaluation_criteria.trim() || null, expected_answer: d.expected_answer.trim() || null,
});

/** A bank row left untouched goes by id (only the knock-out flag is the form's own); anything written or edited goes as text. */
export function draftBody(d: QuestionDraft) {
  return d.question_id ? { question_id: d.question_id, is_knockout: d.is_knockout } : { ...questionBody(d), is_knockout: d.is_knockout };
}

export function isFormRead(data: unknown): data is FormRead {
  const d = data as Partial<FormRead> | null;
  return !!d && Array.isArray(d.templates) && typeof d.can_edit === "boolean" && (d.form === null || Array.isArray(d.form?.questions));
}
export function isSessionsRead(data: unknown): data is SessionsRead {
  const d = data as Partial<SessionsRead> | null;
  return !!d && Array.isArray(d.sessions) && typeof d.can_run === "boolean" && Array.isArray(d.recommendations);
}
export function isComparison(data: unknown): data is Comparison {
  const d = data as Partial<Comparison> | null;
  return !!d && Array.isArray(d.rows) && Array.isArray(d.questions) && Array.isArray(d.versions);
}
