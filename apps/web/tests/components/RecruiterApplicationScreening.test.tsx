import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterApplicationScreening from "@/components/RecruiterApplicationScreening";
import RecruiterRequirementCandidates from "@/components/RecruiterRequirementCandidates";
import type { RecApplication, Screening, ScreeningRead } from "@/lib/recruiterApplications";

// rec-018 (spec §4; AC1, AC2): the screening form on an application -- loading / error, prefill, the full PUT body, Rejected needs
// remarks (blocked before the request), the API's message shown as-is, the read-only summary -- and the board's Screening flag.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const RESULTS = [
  { key: "shortlisted", label: "Shortlisted" }, { key: "hold", label: "Hold" }, { key: "rejected", label: "Rejected" },
  { key: "need_more_info", label: "Need More Information" },
];
const application = (over: Partial<RecApplication> = {}): RecApplication => ({
  id: "A1", job_id: "J1", candidate: { id: "C1", code: "CAN-000001", name: "Rahul Kumar" }, status: "sourced", status_label: "Sourced",
  stage_changed_at: "2026-10-08T05:30:00Z", created_at: "2026-10-08T05:30:00Z", allowed_statuses: [{ key: "screened", label: "Screened" }],
  screening_result: null, ...over,
});
const saved = (over: Partial<Screening> = {}): Screening => ({
  qualification_verified: true, experience_verified: false, skills_verified: true, expected_salary: 650000, notice_days: 30,
  location_preference: "Pune", communication_rating: 4, technical_rating: null, availability: "Immediate", willing_to_relocate: false,
  remarks: "Good fit", result: "hold", result_label: "Hold", screened_by: { id: "r1", full_name: "Riya Recruiter" },
  updated_at: "2026-10-09T05:30:00Z", ...over,
});

let read: ScreeningRead;
let readStatus: number;
let putReply: () => Response;
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  read = { screening: null, results: RESULTS, can_edit: true };
  readStatus = 200;
  putReply = () => res({ screening: saved({ result: "shortlisted", result_label: "Shortlisted" }), application: application({ status: "shortlisted", status_label: "Shortlisted", screening_result: { key: "shortlisted", label: "Shortlisted" } }) });
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "PUT") return Promise.resolve(putReply());
    if (url.endsWith("/screening")) return Promise.resolve(res(read, readStatus));
    if (url.startsWith("/api/v1/recruiter/requirements/J1/candidates"))
      return Promise.resolve(res({ items: [application({ screening_result: { key: "need_more_info", label: "Need More Information" } })], statuses: [], can_add: false }));
    return Promise.resolve(res({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const puts = () => fetchMock.mock.calls.filter(([, init]) => init?.method === "PUT").map(([url, init]) => [url, JSON.parse(init.body)]);
const renderForm = (onSaved = vi.fn()) => {
  render(<RecruiterApplicationScreening applicationId="A1" candidateName="Rahul Kumar" onSaved={onSaved} onCancel={() => {}} />);
  return onSaved;
};

describe("RecruiterApplicationScreening", () => {
  it("loads, then sends the whole form and reports the saved application", async () => {
    const onSaved = renderForm();
    expect(screen.getByText("Loading screening…")).toBeTruthy();
    const form = await screen.findByRole("form", { name: "Screening of Rahul Kumar" });
    fireEvent.click(within(form).getByLabelText("Qualification verified"));
    fireEvent.change(within(form).getByLabelText("Expected salary (per year)"), { target: { value: "650000" } });
    fireEvent.change(within(form).getByLabelText("Notice period (days)"), { target: { value: "30" } });
    fireEvent.change(within(form).getByLabelText("Communication skills"), { target: { value: "4" } });
    fireEvent.change(within(form).getByLabelText("Willing to relocate"), { target: { value: "yes" } });
    fireEvent.change(within(form).getByLabelText("Result"), { target: { value: "shortlisted" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save screening" }));
    await vi.waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(puts()).toEqual([[
      "/api/v1/recruiter/applications/A1/screening",
      {
        qualification_verified: true, experience_verified: false, skills_verified: false, expected_salary: 650000, notice_days: 30,
        location_preference: null, communication_rating: 4, technical_rating: null, availability: null, willing_to_relocate: true,
        remarks: null, result: "shortlisted",
      },
    ]]);
    expect(onSaved.mock.calls[0][0].status_label).toBe("Shortlisted");
  });

  it("prefills the current screening", async () => {
    read = { screening: saved(), results: RESULTS, can_edit: true };
    renderForm();
    const form = await screen.findByRole("form", { name: "Screening of Rahul Kumar" });
    expect((within(form).getByLabelText("Qualification verified") as HTMLInputElement).checked).toBe(true);
    expect((within(form).getByLabelText("Expected salary (per year)") as HTMLInputElement).value).toBe("650000");
    expect((within(form).getByLabelText("Result") as HTMLSelectElement).value).toBe("hold");
    expect((within(form).getByLabelText("Willing to relocate") as HTMLSelectElement).value).toBe("no");
    expect(screen.getByText(/Last saved by Riya Recruiter/)).toBeTruthy();
  });

  it("AC2: Rejected needs remarks before anything is sent", async () => {
    renderForm();
    const form = await screen.findByRole("form", { name: "Screening of Rahul Kumar" });
    fireEvent.change(within(form).getByLabelText("Result"), { target: { value: "rejected" } });
    expect(within(form).getByLabelText("Recruiter remarks (required for Rejected)").getAttribute("aria-required")).toBe("true");
    fireEvent.click(within(form).getByRole("button", { name: "Save screening" }));
    expect((await within(form).findByRole("alert")).textContent).toBe("Remarks are required when the result is Rejected.");
    expect(puts()).toEqual([]);
  });

  it("shows the API's message when the save is refused", async () => {
    putReply = () => res({ detail: "Only an open application can be screened. Reopen it first." }, 409);
    renderForm();
    const form = await screen.findByRole("form", { name: "Screening of Rahul Kumar" });
    fireEvent.change(within(form).getByLabelText("Result"), { target: { value: "hold" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save screening" }));
    expect((await within(form).findByRole("alert")).textContent).toBe("Only an open application can be screened. Reopen it first.");
  });

  it("shows a read-only summary to a reader", async () => {
    read = { screening: saved(), results: RESULTS, can_edit: false };
    renderForm();
    const summary = await screen.findByRole("list", { name: "Screening of Rahul Kumar" });
    expect(within(summary).getByText("Hold")).toBeTruthy();
    expect(within(summary).getByText("6,50,000")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Save screening" })).toBeNull();
  });

  it("says when a reader opens an unscreened application, and when the read fails", async () => {
    read = { screening: null, results: RESULTS, can_edit: false };
    renderForm();
    expect(await screen.findByText("Not screened yet.")).toBeTruthy();
    cleanup();
    readStatus = 500;
    renderForm();
    expect((await screen.findByRole("alert")).textContent).toBe("Unable to load the screening.");
  });
});

describe("RecruiterRequirementCandidates screening flag", () => {
  it("shows the result badge and opens the screening", async () => {
    render(<RecruiterRequirementCandidates requirementId="J1" />);
    const list = await screen.findByRole("list", { name: "Candidates on this requirement" });
    expect(within(list).getByText("Screening: Need More Information")).toBeTruthy();
    fireEvent.click(within(list).getByRole("button", { name: "Screening of Rahul Kumar" }));
    expect(await screen.findByRole("form", { name: "Screening of Rahul Kumar" })).toBeTruthy();
  });
});
