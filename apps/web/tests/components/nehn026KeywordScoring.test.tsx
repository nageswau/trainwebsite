import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import QuestionImportPanel from "@/components/QuestionImportPanel";
import TeacherWorkspaceActions from "@/components/TeacherWorkspaceActions";

// nehn-026 (DEC-SCOPE-333): the trainer types keywords on a written-answer question, and the grading card shows the keyword
// suggestion -- matched / missing keywords, the score pre-filled and still editable.
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const assessment = { id: "a1", batch_id: "b1", batch: "Batch A", title: "Quiz", status: "draft", scheduled_at: "2026-11-01T10:00:00Z", duration_minutes: 30, max_score: 10, pass_percent: 50, attempts_allowed: 1, instructions: "", description: "", publish_results: true, attempt_count: 0 };
const keywordAnswer = { id: "x1", question_id: "q1", prompt: "Name the letters", question_type: "text", max_score: 10, value: "alpha and delta", auto_graded: false, score: 4, auto_score: 4, score_source: "keyword", keywords: ["alpha", "beta", "gamma", "delta", "epsilon"], matched_keywords: ["alpha", "delta"], match_percent: 40 };
const plainAnswer = { id: "x2", question_id: "q2", prompt: "Your week", question_type: "text", max_score: 5, value: "Busy", auto_graded: false, score: null, auto_score: null, score_source: null, keywords: [], matched_keywords: [], match_percent: null };

function serve(answers: unknown[]) {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    const path = String(url);
    if (init?.method === "POST") return Promise.resolve(res({ id: "new", position: 1 }, 201));
    if (path.includes("/trainer/context")) return Promise.resolve(res({ batches: [], students: [], enrollments: [] }));
    if (path.endsWith("/trainer/assessments")) return Promise.resolve(res([assessment]));
    if (path.endsWith("/trainer/assessment-attempts")) return Promise.resolve(res([{ id: "t1", assessment: "Quiz", student: "Asha", status: "submitted", max_score: 15 }]));
    if (path.endsWith("/trainer/assessment-attempts/t1")) return Promise.resolve(res({ id: "t1", assessment: "Quiz", student: "Asha", status: "submitted", feedback: null, answers }));
    return Promise.resolve(res([]));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("nehn-026 keyword scoring", () => {
  it("sends the typed keywords with a written-answer question", async () => {
    const fetchMock = serve([]);
    render(<TeacherWorkspaceActions section="assessments" />);
    await screen.findByRole("option", { name: "Quiz · Batch A" });
    fireEvent.change(document.getElementById("question-assessment") as HTMLSelectElement, { target: { value: "a1" } });
    fireEvent.change(screen.getByLabelText("Question type"), { target: { value: "text" } });
    fireEvent.change(screen.getByLabelText("Question"), { target: { value: "Explain loops" } });
    fireEvent.change(screen.getByLabelText(/^Keywords/), { target: { value: " for loop, loop|iteration ,, while " } });
    fireEvent.click(screen.getByRole("button", { name: "Add question" }));
    await screen.findByText("Question added.");
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(JSON.parse(String(post?.[1]?.body)).keywords).toEqual(["for loop", "loop|iteration", "while"]);
  });

  it("shows the keyword suggestion, the matched and missing keywords, and pre-fills the score", async () => {
    serve([keywordAnswer, plainAnswer]);
    render(<TeacherWorkspaceActions section="assessments" />);
    fireEvent.change(await screen.findByLabelText("Submitted attempt"), { target: { value: "t1" } });
    const item = (await screen.findByText("Name the letters")).closest(".qa-item") as HTMLElement;
    expect(within(item).getByText("Keyword score · 4/10 · 40% matched")).toBeTruthy();
    expect(within(item).getByText("Matched: alpha, delta")).toBeTruthy();
    expect(within(item).getByText("Missing: beta, gamma, epsilon")).toBeTruthy();
    expect((within(item).getByLabelText("Score (of 10)") as HTMLInputElement).value).toBe("4");
    const plain = screen.getByText("Your week").closest(".qa-item") as HTMLElement;
    expect(within(plain).getByText("Max 5")).toBeTruthy();
    expect(within(plain).queryByText(/Matched:/)).toBeNull();
  });

  it("shows a written question's keywords in the import preview", async () => {
    const preview = { total_rows: 1, errors: [], warnings: [], created: 0, questions: [{ row: 2, question_type: "text", prompt: "Explain loops", options: [], correct_answers: [], keywords: ["for loop", "loop|iteration"], max_score: 4 }] };
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(preview))));
    render(<QuestionImportPanel assessments={[assessment]} loading={false} onImported={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Assessment to fill"), { target: { value: "a1" } });
    fireEvent.change(screen.getByLabelText(/Filled template/), { target: { files: [new File(["x"], "q.xlsx")] } });
    fireEvent.click(screen.getByRole("button", { name: "Check file" }));
    const table = await screen.findByRole("table", { name: "Questions in the file" });
    expect(within(table).getByText("Keywords: for loop, loop|iteration")).toBeTruthy();
  });

  it("labels a trainer override with the original suggestion", async () => {
    serve([{ ...keywordAnswer, score: 3, auto_score: 10, score_source: "trainer", matched_keywords: ["alpha", "beta", "gamma", "delta"], match_percent: 80 }]);
    render(<TeacherWorkspaceActions section="assessments" />);
    fireEvent.change(await screen.findByLabelText("Submitted attempt"), { target: { value: "t1" } });
    expect(await screen.findByText("Trainer score · keyword suggestion 10/10 · 80% matched")).toBeTruthy();
  });
});
