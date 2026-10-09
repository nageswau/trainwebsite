import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterRequirementMatches from "@/components/RecruiterRequirementMatches";
import type { Matches, MatchRow } from "@/lib/recruiterMatching";

// rec-016 (DEC-SCOPE-157; AC1-AC3): the requirement's Matching candidates section -- loading / error + retry / no_skills / empty,
// ranked rows with the per-item breakdown and the status on this requirement, Shortlist (rec-017's add), the weights form, read-only.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const row = (over: Partial<MatchRow> = {}): MatchRow => ({
  id: "C1", candidate_code: "CAN-000001", name: "Rahul Kumar", preferred_role: "Java Developer", current_company: null, experience_months: 24,
  location: "Hyderabad", notice_days: 30, status: "available", score: 100, application: null,
  breakdown: [
    { key: "skill:S1", label: "Java", kind: "required", points: 60, max: 60, matched: true },
    { key: "skill:S2", label: "AWS", kind: "preferred", points: 30, max: 30, matched: true },
    { key: "experience", label: "Experience", kind: "experience", points: 10, max: 10, matched: true },
  ],
  ...over,
});
const matches = (over: Partial<Matches> = {}): Matches => ({
  criteria: {
    skills: [
      { id: "S1", name: "Java", kind: "required", weight: 2, points: 60, in_master: true },
      { id: "S2", name: "AWS", kind: "preferred", weight: 1, points: 30, in_master: true },
      { id: "S3", name: "Weblogic", kind: "required", weight: 2, points: 0, in_master: false },
    ],
    experience: { min_months: 0, max_months: 36, points: 10 },
    location: null,
  },
  reason: null,
  items: [
    row(),
    row({ id: "C2", name: "Priya Shah", score: 70, application: { id: "A2", status: "rejected", status_label: "Rejected" },
      breakdown: [
        { key: "skill:S1", label: "Java", kind: "required", points: 60, max: 60, matched: true },
        { key: "skill:S2", label: "AWS", kind: "preferred", points: 0, max: 30, matched: false },
        { key: "experience", label: "Experience", kind: "experience", points: 10, max: 10, matched: true },
      ] }),
  ],
  total: 2, limit: 20, offset: 0, can_shortlist: true, can_edit_weights: true, ...over,
});

let body: Matches;
let status: number;
let postReply: () => Response;
let putReply: () => Response;
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  body = matches();
  status = 200;
  postReply = () => res({ application: { id: "A1", job_id: "J1", candidate: { id: "C1", code: "CAN-000001", name: "Rahul Kumar" }, status: "shortlisted",
    status_label: "Shortlisted", stage_changed_at: "", created_at: "", allowed_statuses: [], screening_result: null } }, 201);
  putReply = () => res({ requirement: { id: "J1", code: "REQ-000001", skills: [] } });
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "POST") return Promise.resolve(postReply());
    if (init?.method === "PUT") return Promise.resolve(putReply());
    if (url.startsWith("/api/v1/recruiter/requirements/J1/matches")) return Promise.resolve(res(body, status));
    return Promise.resolve(res({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const gets = () => fetchMock.mock.calls.filter(([, init]) => !init?.method).map(([url]) => url as string);
const sent = (method: string) => fetchMock.mock.calls.filter(([, init]) => init?.method === method).map(([url, init]) => [url, JSON.parse(init.body)]);

describe("RecruiterRequirementMatches", () => {
  it("ranks candidates with their score, breakdown and status on this requirement", async () => {
    render(<RecruiterRequirementMatches requirementId="J1" />);
    expect(screen.getByText("Loading matching candidates…")).toBeTruthy();
    const list = await screen.findByRole("list", { name: "Matching candidates" });
    const items = within(list).getAllByRole("listitem", { name: /Rahul Kumar|Priya Shah/ });
    expect(items.map((i) => within(i).getAllByRole("link")[0].textContent)).toEqual(["Rahul Kumar", "Priya Shah"]);
    expect(within(items[0]).getByText("100% match")).toBeTruthy();
    expect(within(items[1]).getByText("70% match")).toBeTruthy();
    expect(within(items[1]).getByText("Rejected")).toBeTruthy();
    expect(within(items[0]).getByText("Not on this requirement")).toBeTruthy();
    const breakdown = within(items[1]).getByRole("list", { name: "Score breakdown for Priya Shah" });
    expect(within(breakdown).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Java: 60 of 60 (matched)", "AWS: 0 of 30 (missing)", "Experience: 10 of 10 (matched)",
    ]);
    expect(screen.getByRole("heading", { name: "Matching candidates (2)" })).toBeTruthy();
    expect(screen.getByText(/Weblogic/).textContent).toContain("not in the Skills Master");
    expect(gets()[0]).toBe("/api/v1/recruiter/requirements/J1/matches?limit=20&offset=0");
  });

  it("explains a requirement without Skills Master skills", async () => {
    body = matches({ reason: "no_skills", items: [], total: 0 });
    render(<RecruiterRequirementMatches requirementId="J1" />);
    expect(await screen.findByText(/Add required or preferred skills from the Skills Master/)).toBeTruthy();
  });

  it("says when no candidate has the required skills", async () => {
    body = matches({ items: [], total: 0 });
    render(<RecruiterRequirementMatches requirementId="J1" />);
    expect(await screen.findByText(/No candidates in the pool have the required skills yet/)).toBeTruthy();
  });

  it("shows an error with Retry", async () => {
    status = 500;
    render(<RecruiterRequirementMatches requirementId="J1" />);
    expect((await screen.findByRole("alert")).textContent).toBe("Unable to load matching candidates.");
    status = 200;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("list", { name: "Matching candidates" })).toBeTruthy();
  });

  it("shortlists a candidate once through rec-017 and tells the page", async () => {
    const onShortlisted = vi.fn();
    render(<RecruiterRequirementMatches requirementId="J1" onShortlisted={onShortlisted} />);
    await screen.findByRole("list", { name: "Matching candidates" });
    expect(screen.queryByRole("button", { name: "Shortlist Priya Shah" })).toBeNull(); // already on the requirement
    fireEvent.click(screen.getByRole("button", { name: "Shortlist Rahul Kumar" }));
    await waitFor(() => expect(onShortlisted).toHaveBeenCalledTimes(1));
    expect(sent("POST")).toEqual([["/api/v1/recruiter/requirements/J1/candidates", { candidate_id: "C1", status: "shortlisted" }]]);
    expect(screen.getByRole("status").textContent).toContain("Rahul Kumar shortlisted.");
    expect(screen.queryByRole("button", { name: "Shortlist Rahul Kumar" })).toBeNull();
    expect(screen.getAllByText("Shortlisted").length).toBeGreaterThan(0);
  });

  it("shows the API's refusal when shortlisting fails", async () => {
    postReply = () => res({ detail: "This candidate is already on this requirement" }, 409);
    render(<RecruiterRequirementMatches requirementId="J1" />);
    await screen.findByRole("list", { name: "Matching candidates" });
    fireEvent.click(screen.getByRole("button", { name: "Shortlist Rahul Kumar" }));
    expect(await screen.findByText("This candidate is already on this requirement")).toBeTruthy();
  });

  it("hides every write for a read-only viewer", async () => {
    body = matches({ can_shortlist: false, can_edit_weights: false });
    render(<RecruiterRequirementMatches requirementId="J1" />);
    await screen.findByRole("list", { name: "Matching candidates" });
    expect(screen.queryByRole("button", { name: /Shortlist/ })).toBeNull();
    expect(screen.queryByRole("link", { name: /Contact/ })).toBeNull();
    expect(screen.queryByRole("button", { name: "Adjust weights" })).toBeNull();
    expect(screen.getByRole("link", { name: "View profile of Rahul Kumar" }).getAttribute("href")).toBe("/recruiter/candidates/C1");
  });

  it("saves new weights, reports the requirement and re-reads the ranking", async () => {
    const onRequirementChanged = vi.fn();
    render(<RecruiterRequirementMatches requirementId="J1" onRequirementChanged={onRequirementChanged} />);
    await screen.findByRole("list", { name: "Matching candidates" });
    fireEvent.click(screen.getByRole("button", { name: "Adjust weights" }));
    const java = screen.getByLabelText("Weight of Java (required)") as HTMLInputElement;
    expect(java.value).toBe("2");
    fireEvent.change(java, { target: { value: "8" } });
    fireEvent.click(screen.getByRole("button", { name: "Save weights" }));
    await waitFor(() => expect(onRequirementChanged).toHaveBeenCalledTimes(1));
    expect(sent("PUT")).toEqual([["/api/v1/recruiter/requirements/J1/skill-weights", { weights: [{ id: "S1", weight: 8 }, { id: "S2", weight: 1 }, { id: "S3", weight: 2 }] }]]);
    expect(onRequirementChanged.mock.calls[0][0]).toMatchObject({ id: "J1" });
    expect(screen.getByRole("status").textContent).toContain("Match weights saved.");
    await waitFor(() => expect(gets().length).toBe(2));
    expect(screen.queryByLabelText("Weight of Java (required)")).toBeNull();
  });

  it("returns focus to Adjust weights after Cancel and after Save (QA-02)", async () => {
    render(<RecruiterRequirementMatches requirementId="J1" />);
    await screen.findByRole("list", { name: "Matching candidates" });
    fireEvent.click(screen.getByRole("button", { name: "Adjust weights" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: "Adjust weights" })));
    fireEvent.click(screen.getByRole("button", { name: "Adjust weights" }));
    fireEvent.click(screen.getByRole("button", { name: "Save weights" }));
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: "Adjust weights" })));
  });

  it("refuses a weight outside 1-10 before sending", async () => {
    render(<RecruiterRequirementMatches requirementId="J1" />);
    await screen.findByRole("list", { name: "Matching candidates" });
    fireEvent.click(screen.getByRole("button", { name: "Adjust weights" }));
    fireEvent.change(screen.getByLabelText("Weight of AWS (preferred)"), { target: { value: "11" } });
    fireEvent.click(screen.getByRole("button", { name: "Save weights" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Each weight must be a whole number from 1 to 10.");
    expect(sent("PUT")).toEqual([]);
  });

  it("rec-019: selects shareable rows only and keeps the dialog's success after the selection clears (QA-01)", async () => {
    postReply = () => res({ share: { id: "S1", channel: "other", channel_label: "Other", requirement: { id: "J1", code: "REQ-000001", title: "Java Dev" },
      company_id: "CO1", contact: null, note: null, message: null, shared_by: { id: "U1", full_name: "Asha" }, created_at: "", can_respond: true, items: [] },
      whatsapp_url: null }, 201);
    const onShared = vi.fn();
    render(<RecruiterRequirementMatches requirementId="J1" requirementLabel="Java Dev" companyId="CO1" onShared={onShared} />);
    fireEvent.click(await screen.findByRole("checkbox", { name: "Select Rahul Kumar to share" }));
    expect(screen.queryByRole("checkbox", { name: "Select Priya Shah to share" })).toBeNull(); // Rejected on this requirement
    fireEvent.click(screen.getByRole("button", { name: "Share selected (1)" }));
    fireEvent.click(screen.getByLabelText(/^Other/));
    fireEvent.click(screen.getByRole("button", { name: "Share 1 profile" }));
    expect(await screen.findByText(/Shared 0 profiles for Java Dev by Other/)).toBeTruthy();
    expect(onShared).toHaveBeenCalled();
    expect(sent("POST")).toEqual([["/api/v1/recruiter/shares", { requirement_id: "J1", candidate_ids: ["C1"], channel: "other" }]]);
    expect(screen.queryByRole("button", { name: /Share selected/ })).toBeNull();
  });
});
