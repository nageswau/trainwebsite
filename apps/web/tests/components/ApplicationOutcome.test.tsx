import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CounselorEvaluationPanel from "@/components/CounselorEvaluationPanel";
import DataTable from "@/components/DataTable";
import OutcomeSummary from "@/components/OutcomeSummary";
import { isTerminal, outcomeChoices, outcomeLabel } from "@/lib/applicationOutcome";

// ccrm-015 (DEC-SCOPE-244): the outcome choices, the counselor's outcome form, the closed / on-hold card and the summary.
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (body: unknown, ok = true, status = 200) => Promise.resolve({ ok, status, json: async () => body });
const row = (over: Record<string, unknown> = {}) => ({ id: "a1", student: "Ravi", university: "U3", reference: null, status: "university_selection", sub_status: null, sub_status_label: null, next_action: null, is_agency: false, outcome: null, outcome_label: null, outcome_summary: null, ...over });

async function card(rows: unknown[], post?: (body: Record<string, unknown>, url: string) => Promise<unknown>) {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => (init?.method === "POST" && post ? post(JSON.parse(String(init.body)), url) : json({ rows })));
  vi.stubGlobal("fetch", fetchMock);
  render(<CounselorEvaluationPanel />);
  return { el: (await screen.findByRole("heading", { name: "Ravi" })).closest(".card") as HTMLElement, fetchMock };
}

describe("outcomeChoices", () => {
  it("offers offer declined only from the offer stage, and nothing once closed or enrolled", () => {
    expect(outcomeChoices("university_selection", null)).toEqual(["rejected", "withdrawn", "deferred", "on_hold"]);
    expect(outcomeChoices("offer", "deferred")).toContain("offer_declined");
    expect(outcomeChoices("offer", "rejected")).toEqual([]);
    expect(outcomeChoices("withdrawn", null)).toEqual([]);
    expect(outcomeChoices("enrolled", null)).toEqual([]);
    expect(isTerminal("visa_refused") && !isTerminal("on_hold")).toBe(true);
    expect(outcomeLabel("on_hold")).toBe("On hold");
  });
});

describe("counselor outcome form", () => {
  it("records a rejection with its reason and next steps", async () => {
    const { el, fetchMock } = await card([row()], () => json({ id: "a1", status: "university_selection", outcome: "rejected" }));
    fireEvent.click(within(el).getByRole("button", { name: "Record outcome" }));
    fireEvent.change(within(el).getByLabelText("Reason"), { target: { value: "Grades below cut-off" } });
    fireEvent.change(within(el).getByLabelText("Suggested next steps (optional)"), { target: { value: "Foundation year" } });
    fireEvent.click(within(el).getByRole("button", { name: "Record outcome" }));
    await waitFor(() => expect(within(el).getByText(/Outcome recorded: Rejected/)).toBeInTheDocument());
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST")!;
    expect(post[0]).toBe("/api/v1/workflows/overseas/applications/a1/outcome");
    expect(JSON.parse(String(post[1]!.body))).toEqual({ outcome: "rejected", reason: "Grades below cut-off", outcome_date: null, next_steps: "Foundation year" });
  });

  it("asks for a review date on hold and who requested a withdrawal, and shows a server refusal", async () => {
    const { el } = await card([row()], () => json({ detail: "The review date cannot be in the past" }, false, 422));
    fireEvent.click(within(el).getByRole("button", { name: "Record outcome" }));
    fireEvent.change(within(el).getByLabelText("Outcome"), { target: { value: "withdrawn" } });
    expect(within(el).getByLabelText("Requested by")).toBeRequired();
    fireEvent.change(within(el).getByLabelText("Outcome"), { target: { value: "on_hold" } });
    const review = within(el).getByLabelText("Review date");
    expect(review).toBeRequired();
    fireEvent.change(review, { target: { value: "2030-01-01" } });
    fireEvent.change(within(el).getByLabelText("Reason"), { target: { value: "Awaiting funds" } });
    fireEvent.click(within(el).getByRole("button", { name: "Record outcome" }));
    await waitFor(() => expect(within(el).getByText("The review date cannot be in the past")).toBeInTheDocument());
  });

  it("a closed card has no stage controls and no outcome form", async () => {
    const { el } = await card([row({ outcome: "rejected", outcome_label: "Rejected", outcome_summary: "Rejected -- Course full" })]);
    expect(within(el).getByText("Rejected -- Course full")).toBeInTheDocument();
    expect(within(el).getByText(/only the Overseas Admin can reopen it/)).toBeInTheDocument();
    for (const name of ["Advance stage", "Update sub-status", "Record outcome", "Resume"]) expect(within(el).queryByRole("button", { name })).toBeNull();
  });

  it("an on-hold card is paused and can be resumed with a reason", async () => {
    const { el, fetchMock } = await card([row({ outcome: "on_hold", outcome_label: "On hold" })], () => json({ id: "a1", outcome: null }));
    expect(within(el).queryByRole("button", { name: "Advance stage" })).toBeNull();
    fireEvent.click(within(el).getByRole("button", { name: "Resume" }));
    fireEvent.change(within(el).getByLabelText("Reason"), { target: { value: "Funds arrived" } });
    fireEvent.click(within(el).getByRole("button", { name: "Resume" }));
    await waitFor(() => expect(within(el).getByText("Application resumed.")).toBeInTheDocument());
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST")!;
    expect(post[0]).toBe("/api/v1/workflows/overseas/applications/a1/outcome/reopen");
  });
});

describe("admin reopen column", () => {
  it("QA-01: the confirmation survives the refresh that clears the row's reopen", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json({ id: "a1", outcome: null })));
    const columns = [{ key: "student", label: "Student" }, { key: "reopen", label: "", type: "reopen_outcome" }];
    const { rerender } = render(<DataTable columns={columns} rows={[{ id: "a1", student: "Ravi", reopen: "a1" }, { id: "a2", student: "Asha", reopen: null }]} label="Applications" />);
    expect(within(screen.getByText("Asha").closest("tr") as HTMLElement).queryByRole("button", { name: "Reopen" })).toBeNull();
    const ravi = () => screen.getByText("Ravi").closest("tr") as HTMLElement;
    fireEvent.click(within(ravi()).getByRole("button", { name: "Reopen" }));
    fireEvent.change(within(ravi()).getByLabelText("Reason"), { target: { value: "Appeal upheld" } });
    fireEvent.click(within(ravi()).getByRole("button", { name: "Reopen" }));
    await waitFor(() => expect(within(ravi()).getByText("Application reopened.")).toBeInTheDocument());
    rerender(<DataTable columns={columns} rows={[{ id: "a1", student: "Ravi", reopen: null }, { id: "a2", student: "Asha", reopen: null }]} label="Applications" />);
    expect(within(ravi()).getByText("Application reopened.")).toBeInTheDocument();
    expect(within(ravi()).queryByRole("button", { name: "Reopen" })).toBeNull();
  });
});

describe("OutcomeSummary", () => {
  it("lists only the details recorded", () => {
    render(<OutcomeSummary outcome={{ outcome: "withdrawn", label: "Withdrawn", outcome_date: "2026-10-23", next_steps: null, new_intake: null, terminal: true, reason: "Chose UK", requested_by: "student" }} />);
    expect(screen.getByText("Withdrawn")).toBeInTheDocument();
    expect(screen.getByText("Chose UK")).toBeInTheDocument();
    expect(screen.getByText("Student")).toBeInTheDocument();
    expect(screen.queryByText("Review date")).toBeNull();
  });
});
