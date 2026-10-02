import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentApplicationDetail from "@/components/AgentApplicationDetail";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const detail = (over: Record<string, unknown> = {}) => ({
  id: "a1", agent_student_id: "r1", student: "Asha Rao", has_login: false, university: "Uni One", university_id: "u1", university_slug: "u1",
  course: "MSc Data", course_id: "c1", intake: "Sep 2027", status: "offer", application_reference: null, submitted_on: null,
  application_deadline: null, offer_deadline: null, nearest_deadline: null, next_action: null, updated_at: "", created_at: "", read_only_reason: null,
  history: [], enrollment_date: null, university_student_id: null, enrollment_confirmed_at: null, enrollment_check: null, visa: null, ...over,
});
const visa = (over: Record<string, unknown> = {}) => ({
  id: "v1", stage: "checklist", checklist: [{ item: "Passport", verification_status: "not_uploaded" }], visa_application_date: null,
  appointment_date: null, interview_date: null, decision: null, decided_at: null, disclaimer: "Visa decisions are made by the authority.", ...over,
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

// GET answers with `get`; a write answers with a fresh `write()` Response (a body reads once).
const api = (get: unknown, write: () => Response = () => json({ application: get })) =>
  vi.fn((_: string, init?: RequestInit) => Promise.resolve(init?.method && init.method !== "GET" ? write() : json({ application: get })));
const writes = (fetchMock: ReturnType<typeof vi.fn>) => fetchMock.mock.calls.filter(([, i]) => i?.method && i.method !== "GET");

function mount(fetchMock: ReturnType<typeof vi.fn>, isMaster = true) {
  vi.stubGlobal("fetch", fetchMock);
  render(<AgentApplicationDetail id="a1" isMaster={isMaster} onChanged={vi.fn()} onClose={vi.fn()} />);
}
const region = () => screen.getByRole("region", { name: "Visa" });

describe("AgentApplicationVisa (AGN-012)", () => {
  it("is absent before an offer", async () => {
    mount(api(detail({ status: "university_selection" })));
    await screen.findByText("Asha Rao — Uni One");
    expect(screen.queryByRole("region", { name: "Visa" })).toBeNull();
  });

  it("starts a case: dates and checklist, the displayed status, focus on the notice (Staff too)", async () => {
    const fetchMock = api(detail(), () => json({ application: detail({ visa: visa() }) }, 201));
    mount(fetchMock, false);
    expect(await screen.findByText("No visa case yet.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Start visa case" }));
    await waitFor(() => expect(screen.getByLabelText("Visa application date (optional)")).toHaveFocus());
    fireEvent.change(screen.getByLabelText("Visa application date (optional)"), { target: { value: "2027-05-01" } });
    fireEvent.click(screen.getByRole("checkbox", { name: "Passport" }));
    fireEvent.click(within(screen.getByRole("form", { name: "Start visa case" })).getByRole("button", { name: "Start visa case" }));
    await waitFor(() => expect(screen.getByText("Visa case started.")).toHaveFocus());
    const [url, init] = writes(fetchMock)[0];
    expect([url, init!.method]).toEqual(["/api/v1/workflows/overseas/agent/crm/applications/a1/visa", "POST"]);
    expect(JSON.parse(String(init!.body))).toEqual({ expected_status: "offer", checklist: ["Passport"], visa_application_date: "2027-05-01", appointment_date: null, interview_date: null });
    expect(within(region()).getByText("Passport: Not uploaded")).toBeInTheDocument();
  });

  it("puts a date-order 422 on the interview field and keeps the entry", async () => {
    const error = [{ type: "value_error", loc: ["body", "interview_date"], msg: "The interview date cannot be before the visa application date" }];
    mount(api(detail({ visa: visa({ stage: "documentation" }) }), () => json({ detail: error }, 422)));
    fireEvent.click(await screen.findByRole("button", { name: "Edit visa details" }));
    fireEvent.change(screen.getByLabelText("Interview date (optional)"), { target: { value: "2027-04-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Save visa details" }));
    const input = screen.getByLabelText("Interview date (optional)");
    await waitFor(() => expect(input).toHaveFocus());
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveValue("2027-04-01");
    expect(screen.getByText("The interview date cannot be before the visa application date")).toHaveAttribute("id", input.getAttribute("aria-describedby"));
    expect(screen.queryByRole("checkbox")).toBeNull(); // past checklist: the checklist is not editable
  });

  it("shows the checklist gate refusal as an alert in the move form", async () => {
    const message = "Cannot advance past the checklist stage -- not yet verified: Passport.";
    const fetchMock = api(detail({ visa: visa() }), () => json({ detail: message }, 422));
    mount(fetchMock);
    fireEvent.click(await screen.findByRole("button", { name: "Move visa stage" }));
    fireEvent.change(screen.getByLabelText("Move to"), { target: { value: "documentation" } });
    fireEvent.click(screen.getByRole("button", { name: "Move" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(message));
    expect(screen.getByRole("alert")).toHaveFocus();
    expect(JSON.parse(String(writes(fetchMock)[0][1]!.body))).toEqual({ expected_stage: "checklist", to_stage: "documentation" });
  });

  it("confirms a skip; Escape goes back to Move", async () => {
    const fetchMock = api(detail({ visa: visa({ stage: "documentation" }) }), () => json({ application: detail({ visa: visa({ stage: "decision" }) }) }));
    mount(fetchMock);
    fireEvent.click(await screen.findByRole("button", { name: "Move visa stage" }));
    fireEvent.change(screen.getByLabelText("Move to"), { target: { value: "decision" } });
    fireEvent.click(screen.getByRole("button", { name: "Move" }));
    const group = screen.getByRole("group", { name: "Confirm move" });
    expect(within(group).getByText(/skips 2 stages/)).toBeInTheDocument();
    fireEvent.keyDown(group, { key: "Escape" });
    await waitFor(() => expect(screen.getByRole("button", { name: "Move" })).toHaveFocus());
    fireEvent.click(screen.getByRole("button", { name: "Move" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, move" }));
    await waitFor(() => expect(screen.getByText("Visa case moved to Decision.")).toHaveFocus());
    expect(writes(fetchMock)).toHaveLength(1);
  });

  it("records a decision once, after confirmation, then is read-only with the disclaimer", async () => {
    const decided = detail({ visa: visa({ stage: "decision", decision: "approved", decided_at: "2026-10-02T10:00:00Z" }) });
    let release: (r: Response) => void = () => {};
    const fetchMock = vi.fn((_: string, init?: RequestInit) =>
      init?.method === "PATCH" ? new Promise<Response>((resolve) => (release = resolve)) : Promise.resolve(json({ application: detail({ visa: visa({ stage: "decision" }) }) })),
    );
    mount(fetchMock);
    expect(await screen.findByText("Visa decisions are made by the authority.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Record decision" }));
    fireEvent.click(screen.getByRole("radio", { name: "Approved" }));
    fireEvent.click(screen.getByRole("button", { name: "Record decision" }));
    const yes = within(screen.getByRole("group", { name: "Confirm decision" })).getByRole("button", { name: "Yes, record decision" });
    fireEvent.click(yes);
    fireEvent.click(yes); // same tick: the in-flight guard drops it
    release(json({ application: decided }));
    await waitFor(() => expect(screen.getByText("Visa decision recorded.")).toHaveFocus());
    expect(writes(fetchMock)).toHaveLength(1);
    expect(JSON.parse(String(writes(fetchMock)[0][1]!.body))).toEqual({ expected_stage: "decision", decision: "approved" });
    expect(within(region()).getByText("Approved")).toBeInTheDocument();
    expect(within(region()).queryByRole("button")).toBeNull();
  });

  it("a 409 reloads the detail and announces the server's words", async () => {
    const fetchMock = api(detail({ visa: visa({ stage: "documentation" }) }), () => json({ detail: "This visa case changed since you opened it -- reload to see its current stage" }, 409));
    mount(fetchMock);
    fireEvent.click(await screen.findByRole("button", { name: "Edit visa details" }));
    fireEvent.click(screen.getByRole("button", { name: "Save visa details" }));
    await waitFor(() => expect(screen.getByText(/changed since you opened it/)).toHaveFocus());
    expect(fetchMock.mock.calls.filter(([, i]) => !i?.method || i.method === "GET")).toHaveLength(2);
    expect(screen.queryByRole("form", { name: "Edit visa details" })).toBeNull();
  });

  it.each([
    [401, /Sign in again/],
    [500, /Something went wrong on our side/],
  ])("a %s keeps the entry with its own message", async (status, text) => {
    mount(api(detail({ visa: visa({ stage: "documentation" }) }), () => json({ detail: "x" }, status)));
    fireEvent.click(await screen.findByRole("button", { name: "Edit visa details" }));
    fireEvent.click(screen.getByRole("button", { name: "Save visa details" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(text));
    expect(screen.getByRole("form", { name: "Edit visa details" })).toBeInTheDocument();
  });

  it("one section form at a time; Cancel returns focus to its opener", async () => {
    mount(api(detail({ visa: visa() })));
    fireEvent.click(await screen.findByRole("button", { name: "Edit visa details" }));
    expect(screen.queryByRole("button", { name: "Enroll student" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Update status" })).toBeNull(); // the application status form is hidden too
    fireEvent.click(within(screen.getByRole("form", { name: "Edit visa details" })).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Edit visa details" })).toHaveFocus());
    fireEvent.click(screen.getByRole("button", { name: "Enroll student" }));
    expect(screen.queryByRole("region", { name: "Visa" })).toBeNull();
  });

  it.each([
    ["withdrawn", { status: "withdrawn", read_only_reason: "withdrawn" }],
    ["enrolled", { status: "enrolled" }],
  ])("a %s application shows its case without actions", async (_, over) => {
    mount(api(detail({ ...over, visa: visa({ stage: "documentation" }) })));
    expect(await screen.findByText("Passport: Not uploaded")).toBeInTheDocument();
    expect(within(region()).queryByRole("button")).toBeNull();
  });
});
