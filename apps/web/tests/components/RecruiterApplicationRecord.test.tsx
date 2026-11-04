import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterCandidateApplications from "@/components/RecruiterCandidateApplications";
import RecruiterRequirementCandidates from "@/components/RecruiterRequirementCandidates";
import type { RecApplication, RequirementCandidates } from "@/lib/recruiterApplications";

// hrc-026 (DEC-SCOPE-394): each row shows its Application ID, source and owner; Rejected asks for a reason (and a note for "Other");
// a rejected row shows its reason; the candidate's applications list shows the ID.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const REASONS = [{ key: "skills_mismatch", label: "Skills do not match" }, { key: "other", label: "Other (see note)" }];
const application = (over: Partial<RecApplication> = {}): RecApplication => ({
  id: "A1", job_id: "J1", candidate: { id: "C1", code: "CAN-000001", name: "Rahul Kumar" }, status: "sourced", status_label: "Sourced",
  stage_changed_at: "2026-10-08T05:30:00Z", created_at: "2026-10-08T05:30:00Z", screening_result: null,
  allowed_statuses: [{ key: "screened", label: "Screened" }, { key: "rejected", label: "Rejected" }],
  code: "JA-000042", source: "recruiter", source_label: "Recruiter", owner: { id: "r1", full_name: "Riya Recruiter" },
  rejection_reason: null, rejection_reason_label: null, ...over,
});

let list: RequirementCandidates;
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  list = { items: [application()], statuses: [{ key: "sourced", label: "Sourced", initial: true }], can_add: true, rejection_reasons: REASONS };
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "POST")
      return Promise.resolve(res({ application: application({ status: "rejected", status_label: "Rejected", rejection_reason: "skills_mismatch", rejection_reason_label: "Skills do not match" }) }));
    if (url.startsWith("/api/v1/recruiter/requirements/J1/candidates")) return Promise.resolve(res(list));
    if (url.endsWith("/applications"))
      return Promise.resolve(res({ items: [{ id: "A1", code: "JA-000042", requirement: { id: "J1", code: "REQ-000001", title: "Java Dev", status_label: "Sourcing" }, company: { id: "K1", name: "Acme" }, status: "sourced", status_label: "Sourced", stage_changed_at: "2026-10-08T05:30:00Z", in_scope: true }] }));
    return Promise.resolve(res({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const posts = () => fetchMock.mock.calls.filter(([, init]) => init?.method === "POST").map(([, init]) => JSON.parse(init.body));

async function openStatus() {
  render(<RecruiterRequirementCandidates requirementId="J1" />);
  const row = (await screen.findByRole("list", { name: "Candidates on this requirement" })).querySelector("li") as HTMLElement;
  fireEvent.click(within(row).getByRole("button", { name: /Change status/ }));
  return row;
}

describe("hrc-026 application record on the requirement board", () => {
  it("shows the Application ID, source and owner on each row", async () => {
    render(<RecruiterRequirementCandidates requirementId="J1" />);
    const row = (await screen.findByRole("list", { name: "Candidates on this requirement" })).querySelector("li") as HTMLElement;
    expect(within(row).getByText(/JA-000042/)).toBeTruthy();
    expect(within(row).getByText(/Source: Recruiter/)).toBeTruthy();
    expect(within(row).getByText(/Owner: Riya Recruiter/)).toBeTruthy();
  });

  it("asks for a reason only when Rejected is chosen, and sends it", async () => {
    const row = await openStatus();
    const status = within(row).getByLabelText("New status");
    fireEvent.change(status, { target: { value: "screened" } });
    expect(within(row).queryByLabelText("Rejection reason")).toBeNull();
    fireEvent.change(status, { target: { value: "rejected" } });
    const reason = within(row).getByLabelText("Rejection reason") as HTMLSelectElement;
    expect(reason.required).toBe(true);
    expect((within(row).getByRole("button", { name: "Save status" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(reason, { target: { value: "skills_mismatch" } });
    fireEvent.click(within(row).getByRole("button", { name: "Save status" }));
    expect(await screen.findByText("Rahul Kumar is now Rejected.")).toBeTruthy();
    expect(posts()).toEqual([{ status: "rejected", rejection_reason: "skills_mismatch" }]);
  });

  it("needs a note for Other", async () => {
    const row = await openStatus();
    fireEvent.change(within(row).getByLabelText("New status"), { target: { value: "rejected" } });
    fireEvent.change(within(row).getByLabelText("Rejection reason"), { target: { value: "other" } });
    const note = within(row).getByLabelText(/^Note/) as HTMLTextAreaElement;
    expect(note.required).toBe(true);
    expect((within(row).getByRole("button", { name: "Save status" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(note, { target: { value: "Joined a competitor" } });
    expect((within(row).getByRole("button", { name: "Save status" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("shows a rejected row's reason", async () => {
    list = { ...list, items: [application({ status: "rejected", status_label: "Rejected", rejection_reason: "skills_mismatch", rejection_reason_label: "Skills do not match" })] };
    render(<RecruiterRequirementCandidates requirementId="J1" />);
    expect(await screen.findByText(/Reason: Skills do not match/)).toBeTruthy();
  });
});

describe("hrc-026 the candidate's applications", () => {
  it("shows each application's ID", async () => {
    render(<RecruiterCandidateApplications candidateId="C1" />);
    expect(await screen.findByText(/JA-000042/)).toBeTruthy();
  });
});
