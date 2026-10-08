import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterCandidateApplications from "@/components/RecruiterCandidateApplications";
import RecruiterRequirementCandidates from "@/components/RecruiterRequirementCandidates";
import type { CandidateApplication, RecApplication, RequirementCandidates } from "@/lib/recruiterApplications";

// rec-017 (spec §5; AC1, AC2): the requirement's Candidates section (loading / empty / error, add, status change from the API's
// allowed statuses, history, the API's 409 shown as-is, read-only viewers) and the candidate's Applications section.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const STATUSES = [
  { key: "sourced", label: "Sourced", next: [], initial: true }, { key: "screened", label: "Screened", next: [], initial: true },
  { key: "shortlisted", label: "Shortlisted", next: [], initial: true }, { key: "interview", label: "Interview", next: [], initial: false },
];
const application = (over: Partial<RecApplication> = {}): RecApplication => ({
  id: "A1", job_id: "J1", candidate: { id: "C1", code: "CAN-000001", name: "Rahul Kumar" }, status: "sourced", status_label: "Sourced",
  stage_changed_at: "2026-10-08T05:30:00Z", created_at: "2026-10-08T05:30:00Z",
  allowed_statuses: [{ key: "screened", label: "Screened" }, { key: "interview", label: "Interview" }], ...over,
});

let list: RequirementCandidates;
let listStatus: number;
let postReply: () => Response;
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  list = { items: [application()], statuses: STATUSES, can_add: true };
  listStatus = 200;
  postReply = () => res({ application: application({ status: "interview", status_label: "Interview" }) });
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "POST") return Promise.resolve(postReply());
    if (url.startsWith("/api/v1/recruiter/requirements/J1/candidates")) return Promise.resolve(res(list, listStatus));
    if (url.endsWith("/history"))
      return Promise.resolve(res({ items: [{ from_status: null, from_label: null, to_status: "sourced", to_label: "Sourced", note: "From LinkedIn", changed_by: { id: "r1", full_name: "Riya Recruiter" }, created_at: "2026-10-08T05:30:00Z" }] }));
    if (url.startsWith("/api/v1/recruiter/candidates?"))
      return Promise.resolve(res({ items: [{ id: "C9", candidate_code: "CAN-000009", name: "Neha Shah" }], total: 1 }));
    return Promise.resolve(res({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const posts = () => fetchMock.mock.calls.filter(([, init]) => init?.method === "POST").map(([url, init]) => [url, JSON.parse(init.body)]);

describe("RecruiterRequirementCandidates", () => {
  it("lists candidates with their status and offers Add to writers", async () => {
    render(<RecruiterRequirementCandidates requirementId="J1" />);
    expect(screen.getByText("Loading candidates…")).toBeTruthy();
    const table = await screen.findByRole("list", { name: "Candidates on this requirement" });
    expect(within(table).getByRole("link", { name: "Rahul Kumar" }).getAttribute("href")).toBe("/recruiter/candidates/C1");
    expect(within(table).getByText("Sourced")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Candidates (1)" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Add candidate" })).toBeTruthy();
  });

  it("shows the empty state and hides writes for a read-only viewer", async () => {
    list = { items: [], statuses: STATUSES, can_add: false };
    render(<RecruiterRequirementCandidates requirementId="J1" />);
    expect(await screen.findByText("No candidates on this requirement yet.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Add candidate" })).toBeNull();
  });

  it("hides Change status when the API allows no move", async () => {
    list = { items: [application({ allowed_statuses: [] })], statuses: STATUSES, can_add: false };
    render(<RecruiterRequirementCandidates requirementId="J1" />);
    await screen.findByRole("list", { name: "Candidates on this requirement" });
    expect(screen.queryByRole("button", { name: /Change status/ })).toBeNull();
    expect(screen.getByRole("button", { name: /History/ })).toBeTruthy();
  });

  it("shows an error with Retry when the list fails", async () => {
    listStatus = 500;
    render(<RecruiterRequirementCandidates requirementId="J1" />);
    expect((await screen.findByRole("alert")).textContent).toBe("Unable to load the candidates.");
    listStatus = 200;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("list", { name: "Candidates on this requirement" })).toBeTruthy();
  });

  it("changes a status from the allowed list with a note", async () => {
    render(<RecruiterRequirementCandidates requirementId="J1" />);
    fireEvent.click(await screen.findByRole("button", { name: /Change status/ }));
    const form = screen.getByRole("form", { name: "Change status of Rahul Kumar" });
    const options = within(form).getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["Choose a status", "Screened", "Interview"]);
    fireEvent.change(within(form).getByLabelText("New status"), { target: { value: "interview" } });
    fireEvent.change(within(form).getByLabelText("Note (optional)"), { target: { value: " Round 1 " } });
    fireEvent.click(within(form).getByRole("button", { name: "Save status" }));
    expect(await screen.findByText("Rahul Kumar is now Interview.")).toBeTruthy();
    expect(posts()).toEqual([["/api/v1/recruiter/applications/A1/status", { status: "interview", note: "Round 1" }]]);
  });

  it("shows the API's 409 message on a refused move", async () => {
    postReply = () => res({ detail: "Joined needs the candidate to be Selected (an offer) first" }, 409);
    render(<RecruiterRequirementCandidates requirementId="J1" />);
    fireEvent.click(await screen.findByRole("button", { name: /Change status/ }));
    const form = screen.getByRole("form", { name: "Change status of Rahul Kumar" });
    fireEvent.change(within(form).getByLabelText("New status"), { target: { value: "screened" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save status" }));
    expect((await within(form).findByRole("alert")).textContent).toBe("Joined needs the candidate to be Selected (an offer) first");
  });

  it("opens the history", async () => {
    render(<RecruiterRequirementCandidates requirementId="J1" />);
    fireEvent.click(await screen.findByRole("button", { name: /History/ }));
    expect(await screen.findByText(/Added as Sourced/)).toBeTruthy();
    expect(screen.getByText(/From LinkedIn/)).toBeTruthy();
  });

  it("adds a picked candidate and reports a duplicate (AC2)", async () => {
    postReply = () => res({ detail: "This candidate is already on this requirement" }, 409);
    render(<RecruiterRequirementCandidates requirementId="J1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Add candidate" }));
    const form = screen.getByRole("form", { name: "Add candidate" });
    expect(within(form).getAllByRole("option").map((o) => o.textContent)).toEqual(["Sourced", "Screened", "Shortlisted"]);
    const box = within(form).getByRole("combobox", { name: "Candidate" });
    fireEvent.change(box, { target: { value: "Neha" } });
    fireEvent.click(await screen.findByRole("option", { name: /Neha Shah/ }));
    fireEvent.change(within(form).getByLabelText("Starting status"), { target: { value: "shortlisted" } });
    fireEvent.click(within(form).getByRole("button", { name: "Add candidate" }));
    expect((await within(form).findByRole("alert")).textContent).toBe("This candidate is already on this requirement");
    expect(posts()).toEqual([["/api/v1/recruiter/requirements/J1/candidates", { candidate_id: "C9", status: "shortlisted" }]]);
  });
});

describe("RecruiterCandidateApplications", () => {
  const row = (over: Partial<CandidateApplication>): CandidateApplication => ({
    id: "A1", requirement: { id: "J1", code: "REQ-000001", title: "Java Developer", status_label: "Sourcing" }, company: { id: "K1", name: "ABC Ltd" },
    status: "interview", status_label: "Interview", stage_changed_at: "2026-10-08T05:30:00Z", in_scope: true, ...over,
  });

  it("shows a different status per company and links only in-scope requirements (AC1)", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(res({ items: [
      row({}), row({ id: "A2", requirement: { id: "J2", code: "REQ-000002", title: "QA Engineer", status_label: "Interviewing" }, company: { id: "K2", name: "XYZ Corp" }, status: "rejected", status_label: "Rejected", in_scope: false }),
    ] })));
    render(<RecruiterCandidateApplications candidateId="C1" />);
    const table = await screen.findByRole("list", { name: "Applications" });
    const rows = within(table).getAllByRole("listitem");
    expect(rows.map((r) => r.textContent)).toEqual([
      expect.stringMatching(/^ABC Ltd\s*Interview\s*Java Developer/), expect.stringMatching(/^XYZ Corp\s*Rejected\s*QA Engineer/),
    ]);
    expect(within(table).getByRole("link", { name: "Java Developer" }).getAttribute("href")).toBe("/recruiter/requirements/J1");
    expect(within(table).queryByRole("link", { name: "QA Engineer" })).toBeNull();
  });

  it("shows the empty and error states", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(res({ items: [] })));
    render(<RecruiterCandidateApplications candidateId="C1" />);
    expect(await screen.findByText("Not on any job requirement yet.")).toBeTruthy();
    cleanup();
    fetchMock.mockImplementation(() => Promise.resolve(res({}, 500)));
    render(<RecruiterCandidateApplications candidateId="C1" />);
    await waitFor(() => expect(screen.getByRole("alert").textContent).toBe("Unable to load the applications."));
  });
});
