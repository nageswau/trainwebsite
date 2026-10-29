import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import QuestionImportPanel from "@/components/QuestionImportPanel";

// nehn-025: upload the filled template -> preview with per-row errors -> import (only when every row is valid).
const BASE = "/api/v1/workflows/it/trainer/assessments";
const assessments = [
  { id: "a1", title: "Module 1 Quiz", batch: "Batch A", status: "draft", attempt_count: 0 },
  { id: "a2", title: "Final Test", batch: "Batch A", status: "scheduled", attempt_count: 3 },
];
const question = { row: 2, question_type: "mcq_multiple", prompt: "Pick the even numbers", options: ["1", "2", "3", "4"], correct_answers: ["2", "4"], max_score: 2 };
const clean = { total_rows: 1, questions: [question], errors: [], warnings: [{ row: null, message: "The keywords and explanation columns are not saved yet; 1 row fills them in." }], created: 0 };
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

function setup(responses: Response[]) {
  const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(() => Promise.resolve(responses.shift() ?? json({})));
  vi.stubGlobal("fetch", fetchMock);
  const onImported = vi.fn();
  render(<QuestionImportPanel assessments={assessments} loading={false} onImported={onImported} />);
  return { fetchMock, onImported };
}

function choose(name = "quiz.xlsx") {
  fireEvent.change(screen.getByLabelText("Assessment to fill"), { target: { value: "a1" } });
  fireEvent.change(screen.getByLabelText("Filled template (.xlsx or .csv)"), { target: { files: [new File(["x"], name)] } });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("QuestionImportPanel", () => {
  it("offers the template and locks assessments a student has started", () => {
    setup([]);
    expect(screen.getByRole("link", { name: "Download the question template" }).getAttribute("href")).toBe(`${BASE}/question-template.xlsx`);
    expect((screen.getByRole("option", { name: /Final Test/ }) as HTMLOptionElement).disabled).toBe(true);
  });

  it("previews a clean file, then imports it and reports the draft", async () => {
    const { fetchMock, onImported } = setup([json(clean), json({ ...clean, created: 1 }, 201)]);
    choose();
    fireEvent.click(screen.getByRole("button", { name: "Check file" }));
    expect(await screen.findByText("1 question is ready to import into Module 1 Quiz.")).toBeTruthy();
    const table = screen.getByRole("table", { name: "Questions in the file" });
    expect(table.className).toBe("table compact stack"); // QA25-01: without compact the 650px min-width pushes values off a phone
    const cells = within(table).getAllByRole("cell").map(cell => cell.textContent);
    expect(cells).toEqual(["2", "Multiple choice", "Pick the even numbers", "1. 1 · 2. 2 · 3. 3 · 4. 4", "2, 4", "2"]);
    expect(screen.getByText(/keywords and explanation columns are not saved yet/)).toBeTruthy();
    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE}/a1/questions/import`);

    fireEvent.click(screen.getByRole("button", { name: "Import 1 question" }));
    expect(await screen.findByText("1 question imported into Module 1 Quiz. A Draft stays hidden from students until you publish it in Edit assessment.")).toBeTruthy();
    expect(fetchMock.mock.calls[1][0]).toBe(`${BASE}/a1/questions/import?commit=true`);
    expect(onImported).toHaveBeenCalledOnce();
    expect(screen.queryByRole("table", { name: "Questions in the file" })).toBeNull();
  });

  it("lists row errors and does not offer the import", async () => {
    setup([json({ ...clean, questions: [], errors: [{ row: 5, message: "Correct answer 7 is not a filled option (options 1-4 are filled)" }], warnings: [] })]);
    choose();
    fireEvent.click(screen.getByRole("button", { name: "Check file" }));
    expect(await screen.findByText("1 of 1 row has errors. Fix them in the file and check it again -- nothing is imported until every row is valid.")).toBeTruthy();
    const errors = screen.getByRole("table", { name: "Rows with errors" });
    expect(within(errors).getAllByRole("cell").map(cell => cell.textContent)).toEqual(["5", "Correct answer 7 is not a filled option (options 1-4 are filled)"]);
    expect(screen.queryByRole("button", { name: /^Import/ })).toBeNull();
  });

  it("shows a file-level refusal from the server", async () => {
    setup([json({ detail: "Unknown column: answer; Missing required column: type" }, 422)]);
    choose();
    fireEvent.click(screen.getByRole("button", { name: "Check file" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Unknown column: answer; Missing required column: type");
  });

  it("asks for an assessment and a file before checking", async () => {
    const { fetchMock } = setup([]);
    fireEvent.click(screen.getByRole("button", { name: "Check file" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Choose an assessment and a filled template first.");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("drops the preview when another file is chosen", async () => {
    setup([json(clean)]);
    choose();
    fireEvent.click(screen.getByRole("button", { name: "Check file" }));
    await screen.findByRole("table", { name: "Questions in the file" });
    fireEvent.change(screen.getByLabelText("Filled template (.xlsx or .csv)"), { target: { files: [new File(["y"], "other.xlsx")] } });
    await waitFor(() => expect(screen.queryByRole("table", { name: "Questions in the file" })).toBeNull());
  });
});
