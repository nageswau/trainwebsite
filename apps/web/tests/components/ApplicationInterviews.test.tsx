import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ApplicationInterviewsPanel from "@/components/ApplicationInterviewsPanel";
import StudentInterviewsPanel from "@/components/StudentInterviewsPanel";
import { emptyForm, interviewBody, interviewProblem, meetingLink, toForm, type Interview } from "@/lib/applicationInterviews";

// nehn-037 part 4 (DEC-SCOPE-296): the counselor's Interviews panel on an application card, and the student's "My interviews" card.
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (body: unknown, ok = true, status = 200) => Promise.resolve({ ok, status, json: async () => body });
const URL = "/api/v1/workflows/overseas/applications/a1/interviews";
const interview = (over: Partial<Interview> = {}): Interview => ({
  id: "i1", application_id: "a1", scheduled_at: "2026-11-02T09:30:00Z", mode: "online", mode_label: "Online", location: "https://meet.example.edu/x",
  student_note: "Have your passport ready.", outcome: null, outcome_label: "Awaiting result", recorded_by: "Counsellor A", ...over,
});

describe("applicationInterviews lib", () => {
  it("links only http(s) locations", () => {
    expect(meetingLink("https://meet.example.edu/x")).toBe("https://meet.example.edu/x");
    expect(meetingLink("javascript:alert(1)")).toBeNull();
    expect(meetingLink("Main campus, Room 4")).toBeNull();
    expect(meetingLink(null)).toBeNull();
  });

  it("needs a time and refuses a result before the date", () => {
    expect(interviewProblem(emptyForm())).toMatch(/date and time/);
    const now = new Date("2026-10-27T12:00:00Z");
    expect(interviewProblem({ ...emptyForm(), when: "2099-01-01T10:00", outcome: "passed" }, now)).toMatch(/only after the interview date/);
    expect(interviewProblem({ ...emptyForm(), when: "2099-01-01T10:00", outcome: "cancelled" }, now)).toBeNull();
    expect(interviewProblem({ ...emptyForm(), when: "2026-01-01T10:00", outcome: "passed" }, now)).toBeNull();
  });

  it("sends every field for a new interview and only the changes for an edit", () => {
    const form = { when: "2026-11-02T10:00", mode: "phone", location: " ", student_note: "", outcome: "" };
    expect(interviewBody(form)).toEqual({ scheduled_at: new Date("2026-11-02T10:00").toISOString(), mode: "phone", location: null, student_note: null, outcome: null });
    const saved = interview();
    expect(interviewBody({ ...toForm(saved), outcome: "cancelled" }, saved)).toEqual({ outcome: "cancelled" });
    expect(interviewBody(toForm(saved), saved)).toEqual({});
  });
});

describe("ApplicationInterviewsPanel", () => {
  it("shows loading, then the interviews with an empty state when there are none", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json({ interviews: [] })));
    render(<ApplicationInterviewsPanel applicationId="a1" onChanged={vi.fn()} />);
    expect(screen.getByText("Loading interviews…")).toBeInTheDocument();
    expect(await screen.findByText("No admission interviews recorded yet.")).toBeInTheDocument();
  });

  it("lists an interview with its link, note, result and who recorded it", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json({ interviews: [interview()] })));
    render(<ApplicationInterviewsPanel applicationId="a1" onChanged={vi.fn()} />);
    expect(await screen.findByText("Awaiting result")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "https://meet.example.edu/x" })).toHaveAttribute("rel", expect.stringContaining("noopener"));
    expect(screen.getByText("Have your passport ready.")).toBeInTheDocument();
    expect(screen.getByText(/Recorded by Counsellor A/)).toBeInTheDocument();
  });

  it("is read-only on a closed application", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json({ interviews: [interview()] })));
    render(<ApplicationInterviewsPanel applicationId="a1" readOnly onChanged={vi.fn()} />);
    expect(await screen.findByText("Awaiting result")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit interview" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Add interview" })).toBeNull();
  });

  it("shows a load failure with a retry", async () => {
    const fetchMock = vi.fn().mockReturnValueOnce(json({ detail: "Application is outside your assigned scope" }, false, 403)).mockReturnValue(json({ interviews: [] }));
    vi.stubGlobal("fetch", fetchMock);
    render(<ApplicationInterviewsPanel applicationId="a1" onChanged={vi.fn()} />);
    expect(await screen.findByText(/outside your assigned scope/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("No admission interviews recorded yet.")).toBeInTheDocument();
  });

  it("adds an interview and validates before sending", async () => {
    const onChanged = vi.fn();
    const fetchMock = vi.fn((url: string, init?: RequestInit) => (init?.method === "POST" ? json({ interview: interview(), changed: true }, true, 201) : json({ interviews: [] })));
    vi.stubGlobal("fetch", fetchMock);
    render(<ApplicationInterviewsPanel applicationId="a1" onChanged={onChanged} />);
    fireEvent.click(await screen.findByRole("button", { name: "Add interview" }));
    fireEvent.click(screen.getByRole("button", { name: "Save interview" }));
    expect(await screen.findByText("Choose the interview date and time.")).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(0);
    fireEvent.change(screen.getByLabelText("Date and time"), { target: { value: "2026-11-02T10:00" } });
    fireEvent.change(screen.getByLabelText("Mode"), { target: { value: "in_person" } });
    fireEvent.change(screen.getByLabelText("Link or place"), { target: { value: "Main campus" } });
    fireEvent.click(screen.getByRole("button", { name: "Save interview" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Interview saved."));
    const [, init] = fetchMock.mock.calls.find(([, i]) => i?.method === "POST")!;
    expect(JSON.parse(String(init!.body))).toMatchObject({ mode: "in_person", location: "Main campus", outcome: null });
    expect(fetchMock.mock.calls.find(([, i]) => i?.method === "POST")![0]).toBe(URL);
  });

  it("records a result and shows a server error", async () => {
    const fetchMock = vi.fn((_url: string, init?: RequestInit) =>
      init?.method === "PATCH" ? json({ detail: "A result can be recorded only after the interview date -- or mark it cancelled" }, false, 422) : json({ interviews: [interview({ scheduled_at: "2026-01-02T09:30:00Z" })] }),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<ApplicationInterviewsPanel applicationId="a1" onChanged={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit interview" }));
    fireEvent.change(screen.getByLabelText("Result"), { target: { value: "passed" } });
    fireEvent.click(screen.getByRole("button", { name: "Save interview" }));
    expect(await screen.findByText(/only after the interview date/)).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls.find(([, i]) => i?.method === "PATCH")!;
    expect(url).toBe(`${URL}/i1`);
    expect(JSON.parse(String(init!.body))).toEqual({ outcome: "passed" });
  });
});

describe("StudentInterviewsPanel", () => {
  it("shows the student's interviews with the university and the result", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json({ items: [interview({ outcome: "passed", outcome_label: "Passed", university: "Oxford Brookes", application_code: "APP-000001", recorded_by: undefined })] })));
    render(<StudentInterviewsPanel />);
    expect(screen.getByText("Loading interviews…")).toBeInTheDocument();
    expect(await screen.findByText("Oxford Brookes")).toBeInTheDocument();
    expect(screen.getByText("Passed")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "https://meet.example.edu/x" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Edit/ })).toBeNull();
  });

  it("has an empty state and a retry", async () => {
    const fetchMock = vi.fn().mockReturnValueOnce(json({ detail: "Server error" }, false, 500)).mockReturnValue(json({ items: [] }));
    vi.stubGlobal("fetch", fetchMock);
    render(<StudentInterviewsPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Try again" }));
    expect(await screen.findByText("No admission interviews are scheduled yet.")).toBeInTheDocument();
  });
});
