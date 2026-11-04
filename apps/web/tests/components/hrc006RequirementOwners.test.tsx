import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterRequirementDetail from "@/components/RecruiterRequirementDetail";
import type { Owner, OwnerChange, Requirement } from "@/lib/recruiterRequirements";

// hrc-006 (DEC-SCOPE-384 O11/O12): the requirement's Owners card and its Ownership history. The server decides every rule; these check
// what is shown, what is sent, and how an answer or a refusal reads.
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn(), replace: vi.fn() }), usePathname: () => "/x" }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const PERMS = { can_edit: true, can_change_status: true, can_reassign: false, can_view_matches: false, can_manage_owners: true, can_view_candidates: true };
const officer: Owner = {
  user: { id: "P1", full_name: "Pooja Officer", active: true, email: "pooja@x.local" }, role: "placement_officer", role_label: "Placement officer owner",
  added_by: { id: "U1", full_name: "Rita Recruiter", active: true }, added_at: "2026-11-04T05:00:00Z",
};
const collaborator: Owner = { ...officer, user: { id: "C1", full_name: "Kiran Collab", active: true, email: "kiran@x.local" }, role: "collaborator", role_label: "Collaborator" };
const requirement = (over: Partial<Requirement> = {}) =>
  ({
    id: "R1", code: "REQ-0001", title: "Java Dev", company: { id: "CO1", code: "CO-1", name: "Acme" }, location: "Pune", status: "sourcing", status_label: "Sourcing",
    phase: "open", phase_label: "Open", source: "recruiter", priority: null, vacancies: 2, closes_on: null, requirement_date: null, deadline_state: null,
    assigned_recruiter: { id: "U1", full_name: "Rita Recruiter", active: true }, permissions: PERMS, description: "", department: null, job_category: null, qualification: null,
    experience_min_months: null, experience_max_months: null, salary_min: null, salary_max: null, work_mode: null, shift: null, employment_type: null,
    joining_requirement: null, skills: [], joined_count: 0, allowed_statuses: [], status_history: [], created_by: null, created_at: "2026-11-01T00:00:00Z",
    updated_at: "2026-11-04T04:00:00Z", approval: { required: false, submitted_by: null, submitted_at: null, can_submit: false, can_decide: false },
    owners: [officer, collaborator], visibility: { key: "public", label: "Public website", segment_pool: null, can_change: false }, ...over,
  }) as Requirement;
const change = (id: string, over: Partial<OwnerChange> = {}): OwnerChange => ({
  id, user: { id: "C1", full_name: "Kiran Collab", active: true }, role: "collaborator", role_label: "Collaborator", action: "added", reason: null,
  changed_by: { id: "U1", full_name: "Rita Recruiter", active: true }, created_at: "2026-11-04T05:00:00Z", ...over,
});

let calls: { url: string; method: string; body: Record<string, unknown> }[];
let replies: Response[];
let history: (url: string) => Response;

beforeEach(() => {
  calls = [];
  replies = [];
  history = () => res({ items: [change("H1")], total: 1, limit: 20, offset: 0 });
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    if (init?.method && init.method !== "GET") {
      calls.push({ url, method: init.method, body: init.body ? JSON.parse(String(init.body)) : {} });
      return Promise.resolve(replies.shift()!);
    }
    if (url.includes("/assignment-options")) return Promise.resolve(res({ items: [{ id: "N1", full_name: "Neha New", email: "neha@x.local", role: "placement_team" }], total: 1 }));
    if (url.includes("/assignment-history")) return Promise.resolve(history(url));
    return Promise.resolve(res({ items: [], total: 0, versions: [] }));
  }));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const card = () => screen.getByRole("region", { name: "Owners" });

describe("hrc-006 owners card", () => {
  it("lists the primary, the placement officer owner and the collaborators", () => {
    render(<RecruiterRequirementDetail initial={requirement()} initialJd={null} />);
    const owners = within(card()).getAllByRole("listitem").map((li) => li.textContent);
    expect(owners[0]).toMatch(/Rita Recruiter.*Primary owner/);
    expect(owners[1]).toMatch(/Pooja Officer.*Placement officer owner.*pooja@x\.local/);
    expect(owners[2]).toMatch(/Kiran Collab.*Collaborator/);
    expect(within(card()).getAllByText(/added by Rita Recruiter/)).toHaveLength(2);
    expect(within(card()).getAllByRole("button", { name: /^Remove / })).toHaveLength(2); // never the primary
  });

  it("adds a collaborator picked from the server's options", async () => {
    replies = [res({ requirement: requirement({ owners: [officer, collaborator, { ...collaborator, user: { id: "N1", full_name: "Neha New", active: true, email: "neha@x.local" } }] }) }, 201)];
    render(<RecruiterRequirementDetail initial={requirement()} initialJd={null} />);
    expect(within(card()).getByRole("combobox", { name: "Owner role" })).toHaveValue("collaborator");
    fireEvent.change(within(card()).getByRole("combobox", { name: "Person" }), { target: { value: "neh" } });
    fireEvent.click(await screen.findByRole("option", { name: /Neha New/ }));
    fireEvent.click(within(card()).getByRole("button", { name: "Add owner" }));
    await waitFor(() => expect(screen.getByText("Neha New added as Collaborator.")).toBeTruthy());
    expect(calls[0]).toEqual({ url: "/api/v1/recruiter/requirements/R1/assignments", method: "POST", body: { user_id: "N1", role: "collaborator" } });
    expect(vi.mocked(fetch).mock.calls.some(([u]) => String(u).includes("assignment-options?role=collaborator"))).toBe(true);
  });

  it("removes an owner after a confirmation, and shows a refusal as it came", async () => {
    replies = [res({ detail: "Only the primary owner or a placement manager can change the owners" }, 403), res({ requirement: requirement({ owners: [officer] }) })];
    render(<RecruiterRequirementDetail initial={requirement()} initialJd={null} />);
    fireEvent.click(within(card()).getByRole("button", { name: "Remove Kiran Collab" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, remove" }));
    await waitFor(() => expect(screen.getByText("Only the primary owner or a placement manager can change the owners")).toBeTruthy());
    fireEvent.click(within(card()).getByRole("button", { name: "Remove Kiran Collab" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, remove" }));
    await waitFor(() => expect(screen.getByText("Kiran Collab removed from the owners.")).toBeTruthy());
    expect(calls[1]).toMatchObject({ url: "/api/v1/recruiter/requirements/R1/assignments/C1", method: "DELETE" });
    expect(within(card()).queryByText("Kiran Collab")).toBeNull();
  });

  it("is read-only without can_manage_owners", () => {
    render(<RecruiterRequirementDetail initial={requirement({ permissions: { ...PERMS, can_manage_owners: false } })} initialJd={null} />);
    expect(within(card()).queryByRole("button", { name: /Remove|Add owner/ })).toBeNull();
    expect(within(card()).queryByRole("combobox")).toBeNull();
  });

  it("says when there are no co-owners", () => {
    render(<RecruiterRequirementDetail initial={requirement({ owners: [] })} initialJd={null} />);
    expect(within(card()).getByText(/No placement officer owner or collaborators yet/)).toBeTruthy();
  });
});

describe("hrc-006 ownership history", () => {
  it("reads the history newest first and pages with Show more", async () => {
    history = (url) => url.includes("offset=1")
      ? res({ items: [change("H2", { user: { id: "U1", full_name: "Rita Recruiter", active: true }, role: "primary", role_label: "Primary owner", changed_by: null, reason: "backfill" })], total: 2, limit: 1, offset: 1 })
      : res({ items: [change("H1")], total: 2, limit: 1, offset: 0 });
    render(<RecruiterRequirementDetail initial={requirement()} initialJd={null} />);
    const region = await screen.findByRole("region", { name: "Ownership history" });
    await waitFor(() => expect(within(region).getByText(/Rita Recruiter added Kiran Collab as Collaborator/)).toBeTruthy());
    fireEvent.click(within(region).getByRole("button", { name: "Show more" }));
    await waitFor(() => expect(within(region).getByText(/The system added Rita Recruiter as Primary owner \(recorded before ownership history\)/)).toBeTruthy());
    expect(within(region).queryByRole("button", { name: "Show more" })).toBeNull();
  });

  it("says 'themselves' when the actor is the person (QA-01)", async () => {
    history = () => res({ items: [change("H3", { user: { id: "U1", full_name: "Rita Recruiter", active: true }, role: "primary", role_label: "Primary owner" })], total: 1, limit: 20, offset: 0 });
    render(<RecruiterRequirementDetail initial={requirement()} initialJd={null} />);
    const region = await screen.findByRole("region", { name: "Ownership history" });
    await waitFor(() => expect(within(region).getByText(/Rita Recruiter added themselves as Primary owner/)).toBeTruthy());
  });

  it("offers a retry when the history cannot load", async () => {
    history = () => res({ detail: "boom" }, 500);
    render(<RecruiterRequirementDetail initial={requirement()} initialJd={null} />);
    const region = await screen.findByRole("region", { name: "Ownership history" });
    await waitFor(() => expect(within(region).getByText("Unable to load the ownership history.")).toBeTruthy());
    history = () => res({ items: [change("H1")], total: 1, limit: 20, offset: 0 });
    fireEvent.click(within(region).getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(within(region).getByText(/added Kiran Collab/)).toBeTruthy());
  });
});

describe("hrc-006 placement officer view", () => {
  it("hides the candidate-side sections and the company link", () => {
    render(<RecruiterRequirementDetail initial={requirement({ permissions: { ...PERMS, can_manage_owners: false, can_view_candidates: false } })} initialJd={null} showRevenue />);
    expect(screen.queryByRole("link", { name: /Acme/ })).toBeNull();
    expect(screen.getByText("Acme (CO-1)")).toBeTruthy();
    const urls = vi.mocked(fetch).mock.calls.map(([u]) => String(u));
    expect(urls.some((u) => u.includes("/candidates") || u.includes("/shares") || u.includes("/revenue"))).toBe(false);
  });
});
