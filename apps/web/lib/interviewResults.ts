// hrc-030 (DEC-SCOPE-409): interview results and their release -- the approver's queue, the candidate's own released results and the
// recruiter's view of whether the candidate has been told. The API decides who may publish (`can_release`) and what a candidate sees.
import { isPage, type Page } from "@/lib/apiErrors";

export const RESULTS_URL = "/api/v1/recruiter/interview-results";
export const MY_RESULTS_URL = "/api/v1/candidate/results";
export const RESULTS_PATH = "/it/hr-manager/results";
export const MESSAGE_MAX = 1000;

export type ResultState = "pending_approval" | "released";
export const STATES: { key: ResultState; label: string }[] = [
  { key: "pending_approval", label: "Waiting for approval" },
  { key: "released", label: "Published" },
];
export const parseState = (value: unknown): ResultState => (value === "released" ? "released" : "pending_approval");

/** R10: the result on a recruiter's interview read. */
export type InterviewResult = {
  id: string; outcome: "selected" | "rejected"; outcome_label: string; is_final: boolean; state: ResultState; state_label: string;
  candidate_message: string; release_mode: "auto" | "approval" | null; released_at: string | null;
};
/** R11: one queue row. */
export type ResultRow = InterviewResult & {
  interview: { id: string; code: string; round: string; scheduled_at: string };
  candidate: { id: string; code: string; name: string };
  requirement: { id: string; code: string; title: string };
  company: { id: string; name: string };
  decided_by: { id: string; full_name: string } | null;
  decided_at: string;
  can_release: boolean;
};
export type ResultQueue = Page<ResultRow> & { counts: Record<ResultState, number> };
export type ResultSettings = { auto_release: boolean; can_edit: boolean };

export function isResultQueue(data: unknown): data is ResultQueue {
  return isPage(data) && typeof (data as Partial<ResultQueue>).counts === "object";
}

/** R9: a candidate's own released result. */
export type MyResult = { id: string; round: string; role: string; company: string; outcome: string; outcome_label: string; message: string; released_at: string };
export function isMyResults(data: unknown): data is { items: MyResult[] } {
  return !!data && typeof data === "object" && Array.isArray((data as { items?: unknown }).items);
}

export const releaseUrl = (id: string) => `${RESULTS_URL}/${encodeURIComponent(id)}/release`;
export const PAGE_SIZE = 50;
export const queueUrl = (state: ResultState, offset = 0) => `${RESULTS_URL}?state=${state}&limit=${PAGE_SIZE}&offset=${offset}`;
/** QA-02: the page's `offset` query value -- a whole number, else the first page. */
export const parseOffset = (value: unknown): number => {
  const n = typeof value === "string" && /^\d+$/.test(value) ? Number(value) : 0;
  return Number.isSafeInteger(n) ? n : 0;
};
export const pageHref = (state: ResultState, offset: number) => `${RESULTS_PATH}?state=${state}&offset=${offset}`;
