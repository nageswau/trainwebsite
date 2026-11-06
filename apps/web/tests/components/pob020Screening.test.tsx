import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterScreeningBank from "@/components/RecruiterScreeningBank";
import RecruiterScreeningForm from "@/components/RecruiterScreeningForm";
import RecruiterScreeningSessions from "@/components/RecruiterScreeningSessions";
import type { FormQuestion, FormRead, ScreeningForm, Session, SessionsRead } from "@/lib/recruiterScreening";
import { draftBody, draftOf, failedKnockouts } from "@/lib/recruiterScreening";

// pob-020 (DEC-SCOPE-414): what is shown and sent. The server decides every rule; these check the runner, the builder, the approval and
// the comparison, and how each loading, empty and failed state reads.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const CATALOGUE = {
  categories: [{ key: "technical", label: "Technical skills" }, { key: "availability", label: "Availability and location" }, { key: "compensation", label: "Compensation" }],
  formats: [{ key: "text", label: "Text" }, { key: "yes_no", label: "Yes / No" }, { key: "numeric", label: "Number" }, { key: "choice", label: "Choice" }, { key: "rating", label: "Rating (1-5)" }],
};
const question = (over: Partial<FormQuestion> = {}): FormQuestion => ({
  id: "Q1", question_id: null, position: 1, category: "technical", category_label: "Technical skills", text: "Years with Java?", format: "text", format_label: "Text",
  choices: null, evaluation_criteria: "Hands-on use", expected_answer: "3+", is_knockout: false, ...over,
});
const KNOCKOUT = question({ id: "K1", category: "availability", category_label: "Availability and location", text: "Valid work permit?", format: "yes_no", format_label: "Yes / No", expected_answer: "yes", is_knockout: true });
const SALARY = question({ id: "S1", category: "compensation", category_label: "Compensation", text: "Expected package?" });
const form = (over: Partial<ScreeningForm> = {}): ScreeningForm => ({
  id: "F1", name: "Standard", version: 2, knockout_status: "none", knockout_status_label: "No knock-outs", knockout_approved_by: null, knockout_approved_at: null, questions: [question()], ...over,
});
const session = (over: Partial<Session> = {}): Session => ({
  id: "SE1", kind: "form", form_version: 2, screened_by: { id: "U1", full_name: "Rita Recruiter" }, created_at: "2026-11-05T10:00:00Z", notes: "Call back Friday", recommendation: "hold",
  recommendation_label: "Hold", knockout_triggered: false, knockout_overridden: false, override_reason: null,
  answers: [{ question_id: "Q1", question: "Years with Java?", category: "technical", format: "text", is_knockout: false, answer: "Four", score: 3 }],
  scorecard: { total: 3, max: 5, percent: 60 }, checklist: null, ...over,
});
const read = (over: Partial<SessionsRead> = {}): SessionsRead => ({
  form: form(), sessions: [], can_run: true, sees_compensation: true,
  recommendations: [{ key: "pass", label: "Pass" }, { key: "hold", label: "Hold" }, { key: "reject", label: "Reject" }], ...over,
});
const formRead = (over: Partial<FormRead> = {}): FormRead => ({
  ...CATALOGUE, form: form(), templates: [{ id: "T1", name: "Standard 5-category screening", is_default: true }, { id: "T2", name: "Java", is_default: false }], can_edit: true, can_approve: false, ...over,
});

let fetchMock: ReturnType<typeof vi.fn>;
const posted = (method: string) => fetchMock.mock.calls.filter(([, init]) => init?.method === method).map(([url, init]) => ({ url: String(url), body: JSON.parse(init.body) }));

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderSessions(data: SessionsRead | Response) {
  fetchMock.mockImplementation(async (_url: string, init?: RequestInit) => (init?.method ? res({ session: session() }, 201) : data instanceof Response ? data.clone() : res(data)));
  render(<RecruiterScreeningSessions applicationId="A1" candidateName="Priya" />);
}

describe("RecruiterScreeningSessions", () => {
  it("shows loading, then the history with scorecard, recommendation and answers", async () => {
    renderSessions(read({ sessions: [session()] }));
    expect(screen.getByRole("status")).toHaveTextContent("Loading");
    const list = await screen.findByRole("list", { name: "Screening sessions of Priya" });
    expect(within(list).getByText(/Hold/)).toBeInTheDocument();
    expect(within(list).getByText(/3 \/ 5 \(60%\)/)).toBeInTheDocument();
    expect(within(list).getByText(/Rita Recruiter/)).toBeInTheDocument();
    expect(within(list).getByText("Four")).toBeInTheDocument();
    expect(within(list).getByText(/Call back Friday/)).toBeInTheDocument();
  });

  it("reads a failed load and an empty history clearly", async () => {
    renderSessions(new Response("{}", { status: 500 }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load the screening sessions.");
    cleanup();
    renderSessions(read());
    expect(await screen.findByText("No screening sessions yet.")).toBeInTheDocument();
  });

  it("explains when the requirement has no form", async () => {
    renderSessions(read({ form: null, can_run: false }));
    expect(await screen.findByText(/no screening form yet/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Record a session/ })).not.toBeInTheDocument();
  });

  it("a reader gets no runner", async () => {
    renderSessions(read({ can_run: false, sessions: [session()] }));
    await screen.findByRole("list", { name: "Screening sessions of Priya" });
    expect(screen.queryByRole("button", { name: /Record a session/ })).not.toBeInTheDocument();
  });

  it("sends the form version, answers, scores and notes, once however often it is clicked", async () => {
    renderSessions(read());
    fireEvent.click(await screen.findByRole("button", { name: /Record a session/ }));
    fireEvent.change(screen.getByLabelText(/^Years with Java\?/), { target: { value: "Four" } });
    fireEvent.change(screen.getByLabelText(/Score for Years with Java\?/), { target: { value: "3" } });
    fireEvent.change(screen.getByLabelText("Recommendation"), { target: { value: "pass" } });
    fireEvent.change(screen.getByLabelText("Notes (internal)"), { target: { value: "Strong" } });
    const save = screen.getByRole("button", { name: "Save session" });
    fireEvent.click(save);
    fireEvent.click(save);
    await screen.findByText("Session recorded.");
    expect(posted("POST")).toEqual([
      { url: "/api/v1/recruiter/applications/A1/screening-sessions", body: { form_version: 2, answers: [{ question_id: "Q1", answer: "Four", score: 3 }], notes: "Strong", recommendation: "pass", knockout_override: false, override_reason: null } },
    ]);
  });

  it("leaves unanswered questions out and does not send a score without an answer", async () => {
    renderSessions(read());
    fireEvent.click(await screen.findByRole("button", { name: /Record a session/ }));
    fireEvent.change(screen.getByLabelText("Recommendation"), { target: { value: "hold" } });
    fireEvent.click(screen.getByRole("button", { name: "Save session" }));
    await screen.findByText("Session recorded.");
    expect(posted("POST")[0].body.answers).toEqual([]);
  });

  it("uses the input each format needs", async () => {
    const questions = [question({ id: "N", text: "Numeric?", format: "numeric" }), question({ id: "C", text: "Choice?", format: "choice", choices: ["Pune", "Remote"] }), question({ id: "R", text: "Rating?", format: "rating" }), question({ id: "Y", text: "Yes or no?", format: "yes_no" })];
    renderSessions(read({ form: form({ questions }) }));
    fireEvent.click(await screen.findByRole("button", { name: /Record a session/ }));
    expect(screen.getByLabelText(/^Numeric\?/)).toHaveAttribute("type", "number");
    expect(within(screen.getByLabelText(/^Choice\?/)).getByRole("option", { name: "Remote" })).toBeInTheDocument();
    expect(within(screen.getByLabelText(/^Rating\?/)).getByRole("option", { name: "5" })).toBeInTheDocument();
    expect(within(screen.getByLabelText(/^Yes or no\?/)).getByRole("option", { name: "No" })).toBeInTheDocument();
    expect(screen.queryByLabelText(/Score for Rating\?/)).not.toBeInTheDocument(); // S10: a rating scores itself
  });

  it("AC2: a failed approved knock-out warns, and an override needs a reason", async () => {
    renderSessions(read({ form: form({ knockout_status: "approved", questions: [KNOCKOUT] }) }));
    fireEvent.click(await screen.findByRole("button", { name: /Record a session/ }));
    fireEvent.change(screen.getByLabelText(/^Valid work permit\?/), { target: { value: "no" } });
    expect(screen.getByRole("alert")).toHaveTextContent(/will be saved as Reject/);
    fireEvent.change(screen.getByLabelText("Recommendation"), { target: { value: "pass" } });
    fireEvent.click(screen.getByLabelText("Override the knock-out"));
    fireEvent.click(screen.getByRole("button", { name: "Save session" }));
    expect(await screen.findByText("Give a reason for overriding the knock-out.")).toBeInTheDocument();
    expect(posted("POST")).toEqual([]);
    fireEvent.change(screen.getByLabelText("Reason for the override"), { target: { value: "Renewal confirmed" } });
    fireEvent.click(screen.getByRole("button", { name: "Save session" }));
    await screen.findByText("Session recorded.");
    expect(posted("POST")[0].body).toMatchObject({ knockout_override: true, override_reason: "Renewal confirmed", recommendation: "pass" });
  });

  it("a pending knock-out says so and does not warn", async () => {
    renderSessions(read({ form: form({ knockout_status: "pending", questions: [KNOCKOUT] }) }));
    fireEvent.click(await screen.findByRole("button", { name: /Record a session/ }));
    expect(screen.getByText(/awaiting Team Lead approval/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/^Valid work permit\?/), { target: { value: "no" } });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("S12: compensation questions are left out without the grant, and a hidden answer says so", async () => {
    renderSessions(read({
      sees_compensation: false, form: form({ questions: [question(), SALARY] }),
      sessions: [session({ answers: [{ question_id: "S1", question: "Expected package?", category: "compensation", format: "text", is_knockout: false, answer: null, answer_hidden: true, score: 3 }] })],
    }));
    expect(await screen.findByText(/Hidden/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Record a session/ }));
    expect(screen.queryByLabelText(/^Expected package\?/)).not.toBeInTheDocument();
  });

  it("keeps the entry and reloads the form when it changed (409), and reads a legacy session", async () => {
    let calls = 0;
    fetchMock.mockImplementation(async (_url: string, init?: RequestInit) => {
      if (init?.method) return res({ detail: "The screening form has changed. Reload and answer the current version." }, 409);
      calls += 1;
      return res(read({ form: form({ version: calls + 1 }), sessions: [session({ id: "L", kind: "legacy", form_version: null, answers: [], scorecard: null, notes: "Old", checklist: { result_label: "Need More Information", notice_days: 30, expected_salary: 5 } })] }));
    });
    render(<RecruiterScreeningSessions applicationId="A1" candidateName="Priya" />);
    expect(await screen.findByText(/Checklist: Need More Information/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Record a session/ }));
    fireEvent.change(screen.getByLabelText("Recommendation"), { target: { value: "hold" } });
    fireEvent.click(screen.getByRole("button", { name: "Save session" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("has changed");
    await waitFor(() => expect(calls).toBe(2));
  });
});

describe("RecruiterScreeningForm", () => {
  function renderForm(data: FormRead, comparison: unknown = { version: null, versions: [], questions: [], rows: [], truncated: false }) {
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (String(url).includes("screening-comparison")) return res(comparison);
      if (init?.method) return res({ form: form({ version: 3 }) }, init.method === "POST" ? 201 : 200);
      return res(data);
    });
    render(<RecruiterScreeningForm requirementId="R1" />);
  }
  const open = async () => fireEvent.click(await screen.findByRole("button", { name: "Show screening form" }));

  it("fetches only when opened", async () => {
    renderForm(formRead());
    expect(fetchMock).not.toHaveBeenCalled();
    await open();
    expect(await screen.findByText("Years with Java?")).toBeInTheDocument();
  });

  it("AC1: creates the form from the default or a chosen template", async () => {
    renderForm(formRead({ form: null }));
    await open();
    await screen.findByText(/no screening form yet/i);
    fireEvent.change(screen.getByLabelText("Template"), { target: { value: "T2" } });
    fireEvent.click(screen.getByRole("button", { name: "Create form" }));
    await waitFor(() => expect(posted("POST")).toEqual([{ url: "/api/v1/recruiter/requirements/R1/screening-form", body: { template_id: "T2" } }]));
  });

  it("a reader sees the form without controls, and a load failure reads clearly", async () => {
    renderForm(formRead({ can_edit: false }));
    await open();
    await screen.findByText("Years with Java?");
    expect(screen.queryByRole("button", { name: "Edit questions" })).not.toBeInTheDocument();
    cleanup();
    fetchMock.mockImplementation(async () => new Response("{}", { status: 500 }));
    render(<RecruiterScreeningForm requirementId="R1" />);
    await open();
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load the screening form.");
  });

  it("edits questions into a new version, with a knock-out only on yes/no questions", async () => {
    renderForm(formRead());
    await open();
    fireEvent.click(await screen.findByRole("button", { name: "Edit questions" }));
    expect(screen.queryByLabelText(/^Knock-out/)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Question 1"), { target: { value: "Permit?" } });
    fireEvent.change(screen.getByLabelText("Answer format for question 1"), { target: { value: "yes_no" } });
    fireEvent.click(screen.getByLabelText("Knock-out (question 1)"));
    fireEvent.change(screen.getByLabelText("Candidate must answer (question 1)"), { target: { value: "no" } });
    fireEvent.click(screen.getByRole("button", { name: "Save new version" }));
    await waitFor(() => expect(posted("PUT").length).toBe(1));
    expect(posted("PUT")[0].body.questions[0]).toMatchObject({ text: "Permit?", format: "yes_no", is_knockout: true, expected_answer: "no" });
    expect(await screen.findByText(/Saved as version 3/)).toBeInTheDocument();
  });

  it("refuses an empty question before sending", async () => {
    renderForm(formRead());
    await open();
    fireEvent.click(await screen.findByRole("button", { name: "Edit questions" }));
    fireEvent.change(screen.getByLabelText("Question 1"), { target: { value: "  " } });
    fireEvent.click(screen.getByRole("button", { name: "Save new version" }));
    expect(await screen.findByText("Write every question, or remove it.")).toBeInTheDocument();
    expect(posted("PUT")).toEqual([]);
  });

  it("only a Team Lead sees the approval, which names the version", async () => {
    renderForm(formRead({ form: form({ knockout_status: "pending", knockout_status_label: "Knock-outs awaiting Team Lead approval", questions: [KNOCKOUT] }) }));
    await open();
    await screen.findByText("Knock-outs awaiting Team Lead approval");
    expect(screen.queryByRole("button", { name: "Approve knock-outs" })).not.toBeInTheDocument();
    cleanup();
    fetchMock.mockReset();
    renderForm(formRead({ can_approve: true, form: form({ knockout_status: "pending", questions: [KNOCKOUT] }) }));
    await open();
    fireEvent.click(await screen.findByRole("button", { name: "Approve knock-outs" }));
    await waitFor(() => expect(posted("POST")).toEqual([{ url: "/api/v1/recruiter/requirements/R1/screening-form/approve-knockouts", body: { version: 2 } }]));
  });

  it("AC4: the comparison shows each candidate's scores and recommendation", async () => {
    renderForm(formRead(), {
      version: 2, versions: [2, 1], truncated: true, questions: [question()],
      rows: [{ application_id: "A1", candidate: { id: "C1", code: "C-1", name: "Priya" }, status_label: "Screened", session_id: "S1", created_at: "2026-11-05T10:00:00Z", recommendation: "pass", recommendation_label: "Pass", knockout_triggered: true, knockout_overridden: true, scorecard: { total: 4, max: 5, percent: 80 }, answers: { Q1: { answer: "Four years", score: 4 } } }],
    });
    await open();
    fireEvent.click(await screen.findByRole("button", { name: "Compare candidates" }));
    const table = await screen.findByRole("table", { name: /Screening comparison/ });
    const row = within(table).getByRole("row", { name: /Priya/ });
    expect(row).toHaveTextContent("4 / 5 (80%)");
    expect(row).toHaveTextContent("Pass");
    expect(row).toHaveTextContent("Four years");
    expect(row).toHaveTextContent("Knock-out overridden");
    expect(screen.getByText(/Showing the 50 most recently screened/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Form version"), { target: { value: "1" } });
    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("screening-comparison?version=1"))).toBe(true));
  });

  it("the comparison has an empty state", async () => {
    renderForm(formRead());
    await open();
    fireEvent.click(await screen.findByRole("button", { name: "Compare candidates" }));
    expect(await screen.findByText("No candidate has been screened on this form version.")).toBeInTheDocument();
  });
});

describe("RecruiterScreeningBank", () => {
  const bankRow = { id: "B1", category: "technical", category_label: "Technical skills", text: "Bank question?", format: "text", format_label: "Text", choices: null, evaluation_criteria: null, expected_answer: null, active: true };
  function renderBank(items = [bankRow]) {
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (init?.method === "POST") return res(String(url).includes("templates") ? { template: { id: "T9" } } : { question: { ...bankRow, id: "B2" } }, 201);
      if (init?.method === "PATCH") return res({ question: { ...bankRow, active: false }, template: { id: "T1" } });
      if (String(url).includes("templates")) return res({ ...CATALOGUE, items: [{ id: "T1", name: "Standard", is_default: true, version: 1, archived: false, questions: [question()] }, { id: "T2", name: "Old", is_default: false, version: 1, archived: false, questions: [] }] });
      return res({ ...CATALOGUE, items, total: items.length });
    });
    render(<RecruiterScreeningBank />);
  }

  it("lists questions and templates; the default template cannot be archived", async () => {
    renderBank();
    expect((await screen.findAllByText("Bank question?")).length).toBeGreaterThan(0);
    const templates = await screen.findByRole("list", { name: "Templates" });
    expect(within(templates).getAllByRole("button", { name: /Archive/ })).toHaveLength(1);
  });

  it("shows the empty state and searches on the server", async () => {
    renderBank([]);
    expect(await screen.findByText("No questions match.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Search questions"), { target: { value: "java" } });
    fireEvent.submit(screen.getByRole("search"));
    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => String(url).includes("q=java"))).toBe(true));
  });

  it("adds a question, needing two choices for a choice question", async () => {
    renderBank();
    fireEvent.click(await screen.findByRole("button", { name: "Add question" }));
    fireEvent.change(screen.getByLabelText("Question text"), { target: { value: "New?" } });
    fireEvent.change(screen.getByLabelText("Answer format"), { target: { value: "choice" } });
    fireEvent.change(screen.getByLabelText("Choices (one per line)"), { target: { value: "Only" } });
    fireEvent.click(screen.getByRole("button", { name: "Save question" }));
    expect(await screen.findByText("Give at least two choices.")).toBeInTheDocument();
    expect(posted("POST")).toEqual([]);
    fireEvent.change(screen.getByLabelText("Choices (one per line)"), { target: { value: "One\nTwo" } });
    fireEvent.click(screen.getByRole("button", { name: "Save question" }));
    await waitFor(() => expect(posted("POST")[0]?.body).toMatchObject({ text: "New?", format: "choice", choices: ["One", "Two"] }));
  });

  it("archives a question", async () => {
    renderBank();
    fireEvent.click(await screen.findByRole("button", { name: /Archive Bank question\?/ }));
    await waitFor(() => expect(posted("PATCH")[0]).toEqual({ url: "/api/v1/recruiter/screening/questions/B1", body: { active: false } }));
  });

  it("creates a template from a named set of questions", async () => {
    renderBank();
    fireEvent.click(await screen.findByRole("button", { name: "New template" }));
    fireEvent.change(screen.getByLabelText("Template name"), { target: { value: "Java" } });
    fireEvent.change(screen.getByLabelText("Question 1"), { target: { value: "Spring?" } });
    fireEvent.click(screen.getByRole("button", { name: "Save template" }));
    await waitFor(() => expect(posted("POST")[0]).toMatchObject({ url: "/api/v1/recruiter/screening/templates", body: { name: "Java", questions: [{ text: "Spring?" }] } }));
  });
});

describe("QA fixes", () => {
  it("QA-02: comparison columns are short labels with the questions listed once", async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (String(url).includes("screening-comparison")) {
        return res({ version: 2, versions: [2], truncated: false, questions: [question()], rows: [{ application_id: "A1", candidate: { id: "C1", code: "C-1", name: "Priya" }, status_label: "Screened", session_id: "S1", created_at: "2026-11-05T10:00:00Z", recommendation: "pass", recommendation_label: "Pass", knockout_triggered: false, knockout_overridden: false, scorecard: null, answers: { Q1: { answer: "Four", score: 4 } } }] });
      }
      return res(formRead());
    });
    render(<RecruiterScreeningForm requirementId="R1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Show screening form" }));
    fireEvent.click(await screen.findByRole("button", { name: "Compare candidates" }));
    const table = await screen.findByRole("table", { name: /Screening comparison/ });
    expect(within(table).getByRole("columnheader", { name: "Q1" })).toBeInTheDocument();
    expect(within(table).getAllByRole("cell").find((c) => c.getAttribute("data-label") === "Q1")).toHaveTextContent("4 / 5");
    expect(within(screen.getByRole("list", { name: "Questions compared" })).getByText(/Years with Java\?/)).toBeInTheDocument();
    expect(within(table).queryByRole("rowheader")).not.toBeInTheDocument();
  });

  it("QA-03: a bank question is edited in place", async () => {
    const row = { id: "B1", category: "technical", category_label: "Technical skills", text: "Typpo?", format: "text", format_label: "Text", choices: null, evaluation_criteria: null, expected_answer: null, active: true };
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (init?.method) return res({ question: row });
      return String(url).includes("templates") ? res({ ...CATALOGUE, items: [] }) : res({ ...CATALOGUE, items: [row], total: 1 });
    });
    render(<RecruiterScreeningBank />);
    fireEvent.click(await screen.findByRole("button", { name: /Edit Typpo\?/ }));
    expect(screen.getByLabelText("Question text")).toHaveValue("Typpo?");
    fireEvent.change(screen.getByLabelText("Question text"), { target: { value: "Typo?" } });
    fireEvent.click(screen.getByRole("button", { name: "Save question" }));
    await waitFor(() => expect(posted("PATCH")[0]).toMatchObject({ url: "/api/v1/recruiter/screening/questions/B1", body: { text: "Typo?" } }));
  });

  it("QA-03: a template's questions are edited, including the default's", async () => {
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (init?.method) return res({ template: { id: "T1" } });
      return String(url).includes("templates") ? res({ ...CATALOGUE, items: [{ id: "T1", name: "Standard", is_default: true, version: 1, archived: false, questions: [question()] }] }) : res({ ...CATALOGUE, items: [], total: 0 });
    });
    render(<RecruiterScreeningBank />);
    fireEvent.click(await screen.findByRole("button", { name: /Edit Standard/ }));
    expect(screen.getByLabelText("Template name")).toHaveValue("Standard");
    fireEvent.change(screen.getByLabelText("Question 1"), { target: { value: "Changed?" } });
    fireEvent.click(screen.getByRole("button", { name: "Save template" }));
    await waitFor(() => expect(posted("PATCH")[0]).toMatchObject({ url: "/api/v1/recruiter/screening/templates/T1", body: { name: "Standard", questions: [{ text: "Changed?" }] } }));
  });

  it("QA-04: the form builder adds a question from the bank", async () => {
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (init?.method) return res({ form: form({ version: 3 }) });
      if (String(url).includes("screening/questions")) return res({ ...CATALOGUE, items: [{ id: "B7", category: "technical", category_label: "Technical skills", text: "From the bank?", format: "text", format_label: "Text", choices: null, evaluation_criteria: null, expected_answer: null, active: true }], total: 1 });
      return res(formRead());
    });
    render(<RecruiterScreeningForm requirementId="R1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Show screening form" }));
    fireEvent.click(await screen.findByRole("button", { name: "Edit questions" }));
    fireEvent.change(await screen.findByLabelText("Add from the bank"), { target: { value: "B7" } });
    fireEvent.click(screen.getByRole("button", { name: "Add from bank" }));
    fireEvent.click(screen.getByRole("button", { name: "Save new version" }));
    await waitFor(() => expect(posted("PUT")[0].body.questions.at(-1)).toEqual({ question_id: "B7", is_knockout: false }));
  });

  it("QA-05: the runner closes when a reload shows the application can no longer be screened", async () => {
    let calls = 0;
    fetchMock.mockImplementation(async (_url: string, init?: RequestInit) => {
      if (init?.method) return res({ detail: "Only an open application can be screened. Reopen it first." }, 409);
      calls += 1;
      return res(read({ can_run: calls === 1 }));
    });
    render(<RecruiterScreeningSessions applicationId="A1" candidateName="Priya" />);
    fireEvent.click(await screen.findByRole("button", { name: /Record a session/ }));
    fireEvent.change(screen.getByLabelText("Recommendation"), { target: { value: "hold" } });
    fireEvent.click(screen.getByRole("button", { name: "Save session" }));
    await waitFor(() => expect(screen.queryByRole("form", { name: "Record a screening session" })).not.toBeInTheDocument());
    expect(screen.getByRole("alert")).toHaveTextContent("Only an open application");
  });

  it("QA-06: a legacy session shows its verified and relocate answers in words", async () => {
    renderSessions(read({ sessions: [session({ id: "L", kind: "legacy", form_version: null, answers: [], scorecard: null, notes: null, checklist: { result_label: "Hold", qualification_verified: true, skills_verified: false, willing_to_relocate: true, communication_rating: 4 } })] }));
    const list = await screen.findByRole("list", { name: "Screening sessions of Priya" });
    expect(within(list).getByText(/Qualification verified/).closest("li")).toHaveTextContent("Yes");
    expect(within(list).getByText(/Skills verified/).closest("li")).toHaveTextContent("No");
    expect(within(list).getByText(/Willing to relocate/).closest("li")).toHaveTextContent("Yes");
  });
});

describe("helpers", () => {
  it("failedKnockouts counts only approved forms and answered questions", () => {
    expect(failedKnockouts(form({ knockout_status: "pending", questions: [KNOCKOUT] }), { K1: "no" })).toEqual([]);
    expect(failedKnockouts(form({ knockout_status: "approved", questions: [KNOCKOUT] }), {})).toEqual([]);
    expect(failedKnockouts(form({ knockout_status: "approved", questions: [KNOCKOUT] }), { K1: "yes" })).toEqual([]);
    expect(failedKnockouts(form({ knockout_status: "approved", questions: [KNOCKOUT] }), { K1: "no" })).toEqual([KNOCKOUT]);
  });

  it("a form's own row is sent as its text, so a save never re-copies a changed or archived bank question", () => {
    expect(draftBody(draftOf(question({ question_id: "B9", text: "Form's copy" })))).toMatchObject({ text: "Form's copy" });
    expect(draftBody(draftOf(question({ question_id: "B9" })))).not.toHaveProperty("question_id");
  });

  it("an untouched bank question goes by id; a written one as text", () => {
    expect(draftBody(draftOf({ id: "B1", category: "technical", text: "T", format: "text", choices: null, evaluation_criteria: null, expected_answer: null }, true))).toEqual({ question_id: "B1", is_knockout: false });
    expect(draftBody({ ...draftOf(question()), question_id: null, text: " Edited " })).toMatchObject({ text: "Edited", category: "technical" });
  });
});
