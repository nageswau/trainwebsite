import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterApplicationInterviews from "@/components/RecruiterApplicationInterviews";
import type { InterviewFeedback, RecInterview } from "@/lib/recruiterInterviews";
import { recInterview } from "@/tests/helpers/recruiterInterviews";

// rec-021 (spec §4; FB2-FB5; AC1, AC2): the feedback form on a Completed interview, its validation and the server's refusals, the
// summary every reader sees, and the next round's draft (the schedule form with the suggested round pre-chosen).
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }), usePathname: () => "/recruiter", useSearchParams: () => new URLSearchParams() }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const feedback = (over: Partial<InterviewFeedback> = {}): InterviewFeedback => ({
  technical_rating: 5, communication_rating: null, overall_rating: 4, strengths: "Strong Java", weaknesses: null, recruiter_comments: "Move ahead",
  company_feedback: "Client is keen", next_round: "manager_round", next_round_label: "Manager Round", final_decision: "selected",
  final_decision_label: "Selected", recorded_by: { id: "r1", full_name: "Riya Recruiter" }, updated_at: "2026-10-10T06:30:00Z", ...over,
});
const completed = (over: Partial<RecInterview> = {}) =>
  recInterview({ status: "completed", status_label: "Completed", allowed_statuses: [], can_reschedule: false, can_feedback: true, ...over });

let items: RecInterview[];
let canSchedule: boolean;
let writeReply: () => Response;
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  items = [completed()];
  canSchedule = true;
  writeReply = () => res({ interview: completed({ status: "selected", status_label: "Selected", feedback: feedback() }) });
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method) return Promise.resolve(writeReply());
    if (url.endsWith("/applications/A1/interviews")) return Promise.resolve(res({ items, can_schedule: canSchedule }));
    return Promise.resolve(res({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const writes = () => fetchMock.mock.calls.filter(([, init]) => init?.method).map(([url, init]) => [url, init.method, JSON.parse(init.body)]);
const section = (onChanged = vi.fn()) => render(<RecruiterApplicationInterviews applicationId="A1" candidateName="Rahul Kumar" contacts={[]} onChanged={onChanged} />);
const openForm = async () => {
  fireEvent.click(await screen.findByRole("button", { name: "Record feedback for INT-000001" }));
  return screen.getByRole("form", { name: "Feedback for INT-000001" });
};

describe("Interview feedback", () => {
  it("offers feedback only when the API allows it", async () => {
    items = [recInterview()];
    section();
    await screen.findByRole("list", { name: "Interviews of Rahul Kumar" });
    expect(screen.queryByRole("button", { name: /feedback/i })).toBeNull();
  });

  it("requires the overall rating before sending", async () => {
    section();
    const form = await openForm();
    fireEvent.click(within(form).getByRole("button", { name: "Save feedback" }));
    expect(within(form).getByText("Choose an overall rating")).toBeTruthy();
    expect(within(form).getByLabelText("Overall rating (required)").getAttribute("aria-invalid")).toBe("true");
    expect(writes()).toHaveLength(0);
  });

  it("saves the whole form, reports it and opens the next round's draft (AC2)", async () => {
    const onChanged = vi.fn();
    section(onChanged);
    const form = await openForm();
    fireEvent.change(within(form).getByLabelText("Technical rating"), { target: { value: "5" } });
    fireEvent.change(within(form).getByLabelText("Overall rating (required)"), { target: { value: "4" } });
    fireEvent.change(within(form).getByLabelText("Strengths"), { target: { value: "  Strong Java " } });
    fireEvent.change(within(form).getByLabelText("Company feedback"), { target: { value: "Client is keen" } });
    fireEvent.change(within(form).getByLabelText("Next round"), { target: { value: "manager_round" } });
    fireEvent.change(within(form).getByLabelText("Final decision"), { target: { value: "selected" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save feedback" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Feedback saved. Next round suggested: Manager Round."));
    expect(writes()).toEqual([["/api/v1/recruiter/interviews/I1/feedback", "PUT", {
      technical_rating: 5, communication_rating: null, overall_rating: 4, strengths: "Strong Java", weaknesses: null, recruiter_comments: null,
      company_feedback: "Client is keen", next_round: "manager_round", final_decision: "selected",
    }]]);
    const draft = await screen.findByRole("form", { name: "Schedule interview" });
    expect((within(draft).getByLabelText("Round (required)") as HTMLSelectElement).value).toBe("manager_round");
  });

  it("sends one request when Save feedback is clicked twice in a row", async () => {
    section();
    const form = await openForm();
    fireEvent.change(within(form).getByLabelText("Overall rating (required)"), { target: { value: "3" } });
    const submit = within(form).getByRole("button", { name: "Save feedback" });
    act(() => { submit.click(); submit.click(); });
    await waitFor(() => expect(writes()).toHaveLength(1));
  });

  it("clears and disables the next round when the decision is Rejected", async () => {
    section();
    const form = await openForm();
    const next = within(form).getByLabelText("Next round") as HTMLSelectElement;
    fireEvent.change(next, { target: { value: "manager_round" } });
    fireEvent.change(within(form).getByLabelText("Final decision"), { target: { value: "rejected" } });
    expect(next.value).toBe("");
    expect(next.disabled).toBe(true);
  });

  it("places the server's 422 on its field and keeps a 409 in its words", async () => {
    section();
    const form = await openForm();
    fireEvent.change(within(form).getByLabelText("Overall rating (required)"), { target: { value: "4" } });
    writeReply = () => res({ detail: [{ loc: ["body", "strengths"], msg: "String should have at most 2000 characters", type: "string_too_long" }] }, 422);
    fireEvent.click(within(form).getByRole("button", { name: "Save feedback" }));
    expect(await within(form).findByText("String should have at most 2000 characters")).toBeTruthy();
    writeReply = () => res({ detail: "An interview cannot move from Selected to Rejected" }, 409);
    fireEvent.click(within(form).getByRole("button", { name: "Save feedback" }));
    expect(await within(form).findByText("An interview cannot move from Selected to Rejected")).toBeTruthy();
  });

  it("shows the saved feedback to every reader and pre-fills the edit form", async () => {
    items = [completed({ status: "selected", status_label: "Selected", can_feedback: false, feedback: feedback() })];
    section();
    const summary = await screen.findByRole("list", { name: "Feedback of INT-000001" });
    for (const text of ["Overall: 4 / 5", "Technical: 5 / 5", "Communication: Not rated", "Strengths: Strong Java", "Company feedback: Client is keen",
      "Next round: Manager Round", "Final decision: Selected"]) expect(summary.textContent).toContain(text);
    expect(screen.queryByRole("button", { name: /feedback/i })).toBeNull();
    cleanup();
    items = [completed({ status: "selected", status_label: "Selected", feedback: feedback() })];
    section();
    fireEvent.click(await screen.findByRole("button", { name: "Edit feedback for INT-000001" }));
    const form = screen.getByRole("form", { name: "Feedback for INT-000001" });
    expect((within(form).getByLabelText("Overall rating (required)") as HTMLSelectElement).value).toBe("4");
    expect((within(form).getByLabelText("Strengths") as HTMLTextAreaElement).value).toBe("Strong Java");
  });

  it("offers the newest interview's suggested round as a draft while the application can be scheduled", async () => {
    items = [completed({ status: "selected", status_label: "Selected", feedback: feedback() })];
    section();
    fireEvent.click(await screen.findByRole("button", { name: "+ Schedule Manager Round (suggested) for Rahul Kumar" }));
    const draft = screen.getByRole("form", { name: "Schedule interview" });
    expect((within(draft).getByLabelText("Round (required)") as HTMLSelectElement).value).toBe("manager_round");
    cleanup();
    canSchedule = false;
    section();
    await screen.findByRole("list", { name: "Interviews of Rahul Kumar" });
    expect(screen.queryByRole("button", { name: /suggested/ })).toBeNull();
  });
});
