import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterCandidateTags from "@/components/RecruiterCandidateTags";
import RecruiterFindCandidates from "@/components/RecruiterFindCandidates";
import { clearPermissions } from "@/lib/usePermissions";

// pob-019 (DEC-SCOPE-439): the card's enrichment facts and tags (T5), the tag filter (T4), the bulk bar -- shortlist, share, assign task
// (T7-T12) -- and the candidate page's Tags section (T2).
let query = "";
const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }), usePathname: () => "/recruiter/find-candidates", useSearchParams: () => new URLSearchParams(query),
}));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const HOT = "0f8fad5b-d9cb-469f-a165-70867728950e";
const OLD = "1f8fad5b-d9cb-469f-a165-70867728950e";
const base = {
  candidate_code: "CAN-000001", preferred_role: "Java Developer", current_company: null, experience_months: 36, location: "Hyderabad",
  notice_days: 0, source: { id: "s2", name: "Referral", active: true }, source_detail: null, status: "available", skills: [],
};
const rahul = {
  ...base, id: "c1", name: "Rahul Kumar", owner: { id: "u1", full_name: "Priya Shah" }, last_contacted_at: "2026-11-01T10:00:00Z",
  active_applications: 2, prior_submissions: 1, tags: [{ id: HOT, name: "Hot", active: true }],
  system_tags: [{ kind: "experience", label: "3–5 years" }, { kind: "skill_category", label: "Programming" }],
};
const asha = { ...base, id: "c2", name: "Asha Rao", owner: null, last_contacted_at: null, active_applications: 0, prior_submissions: 0, tags: [], system_tags: [] };
const result = { items: [rahul, asha], total: 2, limit: 50, offset: 0, facets: { experience: [], location: [], availability: [] }, terms: [] };
const requirement = { id: "r1", title: "Java Dev", code: "REQ-1", status: "sourcing", company: { name: "Acme" } };
let fetchMock: ReturnType<typeof vi.fn>;
let bulk: Response;

beforeEach(() => {
  query = "all=java";
  clearPermissions();
  push.mockReset();
  bulk = res({ added: [{ candidate_id: "c1", application_id: "a1" }], skipped: [{ candidate_id: "c2", reason: "do_not_contact", message: "This candidate is marked Do Not Contact" }] });
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (url.startsWith("/api/v1/recruiter/catalogue/candidate-tags")) return Promise.resolve(res({ items: [{ id: HOT, name: "Hot", active: true, sort_order: 0 }], total: 1, limit: 100, offset: 0 }));
    if (url.startsWith("/api/v1/recruiter/catalogue/")) return Promise.resolve(res({ items: [], total: 0, limit: 100, offset: 0 }));
    if (url.startsWith("/api/v1/recruiter/skill-categories")) return Promise.resolve(res({ items: [], total: 0 }));
    if (url === "/api/v1/auth/me/permissions") return Promise.resolve(res({}, 500));
    if (url.startsWith("/api/v1/recruiter/requirements?")) return Promise.resolve(res({ items: [requirement], total: 1 }));
    if (url === "/api/v1/recruiter/requirements/r1/candidates/bulk") return Promise.resolve(bulk);
    if (url.startsWith("/api/v1/recruiter/candidate-tasks/assignees")) return Promise.resolve(res([{ id: "u9", full_name: "Kiran Rao", role: "placement_team" }]));
    if (url === "/api/v1/recruiter/candidate-tasks/bulk") return Promise.resolve(res({ created: [{ candidate_id: "c1", task_id: "t1" }, { candidate_id: "c2", task_id: "t2" }], skipped: [] }, 201));
    if (url === "/api/v1/recruiter/candidates/c1/tags" && init?.method === "PUT") {
      return Promise.resolve(res({ items: JSON.parse(String(init.body)).tag_ids.map((id: string) => ({ id, name: id === HOT ? "Hot" : "Old", active: id === HOT })), can_edit: true }));
    }
    if (url === "/api/v1/recruiter/candidates/c1/tags") return Promise.resolve(res({ items: [{ id: OLD, name: "Old", active: false }], can_edit: true }));
    return Promise.resolve(res(result));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const calls = (url: string) => fetchMock.mock.calls.filter(([u, init]) => u === url && init?.body).map(([, init]) => JSON.parse(String(init.body)));
const card = (name: RegExp) => screen.findByRole("listitem", { name });

async function pickRequirement() {
  fireEvent.change(screen.getByRole("combobox", { name: "Shortlist into requirement" }), { target: { value: "Java" } });
  fireEvent.click(await screen.findByRole("option", { name: /Java Dev — Acme/ }));
}

describe("pob-019 result cards", () => {
  it("shows the owner, last contact, active applications, prior submissions and the tags", async () => {
    render(<RecruiterFindCandidates writes sourceFilter />);
    const r = within(await card(/Rahul Kumar/));
    expect(r.getByText("Owner").nextElementSibling).toHaveTextContent("Priya Shah");
    expect(r.getByText("Last contacted").nextElementSibling?.querySelector("time")).toHaveAttribute("datetime", "2026-11-01T10:00:00Z");
    expect(r.getByText("Active applications").nextElementSibling).toHaveTextContent("2");
    expect(r.getByText("Prior submissions").nextElementSibling).toHaveTextContent("1");
    expect(within(r.getByRole("list", { name: "Tags" })).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["Hot", "3–5 years", "Programming"]);
    const a = within(await card(/Asha Rao/));
    expect(a.getByText("Owner").nextElementSibling).toHaveTextContent("Unassigned");
    expect(a.getByText("Last contacted").nextElementSibling).toHaveTextContent("Never");
    expect(a.queryByRole("list", { name: "Tags" })).toBeNull();
  });

  it("filters by a tag on its own", async () => {
    query = `tag=${HOT}`;
    render(<RecruiterFindCandidates writes sourceFilter />);
    await card(/Rahul Kumar/);
    expect(calls("/api/v1/recruiter/candidates/search?limit=50&offset=0").at(-1)).toEqual({ tag_ids: [HOT] });
    expect(await screen.findByRole("button", { name: "Remove Candidate tags: Hot" })).toBeInTheDocument();
  });
});

describe("pob-019 bulk bar", () => {
  it("offers a select box to writers without a requirement, and needs one to shortlist", async () => {
    render(<RecruiterFindCandidates writes sourceFilter />);
    await card(/Rahul Kumar/);
    fireEvent.click(screen.getByRole("checkbox", { name: "Select Rahul Kumar" }));
    expect(screen.getByRole("button", { name: "Shortlist selected (1)" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Assign task (1)" })).toBeEnabled();
  });

  it("shortlists the selection in one call and reports what was skipped", async () => {
    render(<RecruiterFindCandidates writes sourceFilter />);
    await card(/Rahul Kumar/);
    await pickRequirement();
    fireEvent.click(screen.getByRole("checkbox", { name: "Select Rahul Kumar" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select Asha Rao" }));
    fireEvent.click(screen.getByRole("button", { name: "Shortlist selected (2)" }));
    expect(await screen.findByText("Shortlisted 1 candidate for Java Dev — Acme.")).toBeInTheDocument();
    expect(screen.getByText("Asha Rao: This candidate is marked Do Not Contact")).toBeInTheDocument();
    expect(calls("/api/v1/recruiter/requirements/r1/candidates/bulk")).toEqual([{ candidate_ids: ["c1", "c2"] }]);
    expect(screen.getByRole("checkbox", { name: "Select Asha Rao" })).toBeChecked(); // the skipped stay selected; the added are cleared
    expect(screen.getByRole("checkbox", { name: "Select Rahul Kumar" })).not.toBeChecked();
  });

  it("shows the API's refusal and keeps the selection", async () => {
    bulk = res({ detail: "Candidates cannot be added to a closed or cancelled requirement" }, 409);
    render(<RecruiterFindCandidates writes sourceFilter />);
    await card(/Rahul Kumar/);
    await pickRequirement();
    fireEvent.click(screen.getByRole("checkbox", { name: "Select Rahul Kumar" }));
    fireEvent.click(screen.getByRole("button", { name: "Shortlist selected (1)" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Candidates cannot be added to a closed or cancelled requirement");
    expect(screen.getByRole("checkbox", { name: "Select Rahul Kumar" })).toBeChecked();
  });

  it("assigns one task to every selected candidate", async () => {
    render(<RecruiterFindCandidates writes sourceFilter />);
    await card(/Rahul Kumar/);
    fireEvent.click(screen.getByRole("checkbox", { name: "Select Rahul Kumar" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select Asha Rao" }));
    fireEvent.click(screen.getByRole("button", { name: "Assign task (2)" }));
    const form = within(screen.getByRole("form", { name: "Assign a task to 2 candidates" }));
    fireEvent.change(form.getByLabelText("Task type"), { target: { value: "follow_up" } });
    fireEvent.change(form.getByLabelText("Title"), { target: { value: "Call about Java" } });
    fireEvent.change(form.getByLabelText("Due (IST)"), { target: { value: "2099-01-01T10:00" } });
    fireEvent.change(form.getByRole("combobox", { name: "Assign to" }), { target: { value: "Kiran" } });
    fireEvent.click(await screen.findByRole("option", { name: /Kiran Rao/ }));
    fireEvent.click(form.getByRole("button", { name: "Create 2 tasks" }));
    expect(await screen.findByText("Created 2 tasks.")).toBeInTheDocument();
    expect(calls("/api/v1/recruiter/candidate-tasks/bulk")).toEqual([{
      task_type: "follow_up", title: "Call about Java", due_at: "2099-01-01T10:00:00+05:30", assignee_user_id: "u9", candidate_ids: ["c1", "c2"],
    }]);
  });

  it("offers no selection or bulk bar to readers", async () => {
    render(<RecruiterFindCandidates writes={false} sourceFilter={false} />);
    await card(/Rahul Kumar/);
    expect(screen.queryByRole("checkbox", { name: "Select Rahul Kumar" })).toBeNull();
    expect(screen.queryByRole("button", { name: /Assign task/ })).toBeNull();
  });
});

describe("pob-019 candidate Tags section", () => {
  it("keeps an inactive tag, adds an active one and saves the whole set", async () => {
    render(<RecruiterCandidateTags candidateId="c1" />);
    expect(await screen.findByText("Old (inactive)")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Edit tags" }));
    fireEvent.click(await screen.findByRole("checkbox", { name: "Hot" }));
    expect(screen.getByRole("checkbox", { name: "Old (inactive)" })).toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: "Save tags" }));
    await waitFor(() => expect(calls("/api/v1/recruiter/candidates/c1/tags")).toEqual([{ tag_ids: [OLD, HOT] }]));
    expect(await screen.findByText("Tags saved.")).toBeInTheDocument();
  });
});
