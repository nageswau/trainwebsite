import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterTalentPool from "@/components/RecruiterTalentPool";
import RecruiterTalentPools from "@/components/RecruiterTalentPools";
import { findHref, formOf, type Pool, poolBody, ruleText } from "@/lib/recruiterPools";

// rec-015 (DEC-SCOPE-159): the pools list (managers create), the pool page (members, the P5 warning, Edit for managers) and the rule
// helpers (P2: years <-> months, as on Find Candidates).
const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }), usePathname: () => "/recruiter/pools", useSearchParams: () => new URLSearchParams() }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const pool = (over: Partial<Pool> = {}): Pool => ({
  id: "p1", name: "Cloud Engineers", all: [], any: [["AWS", "Azure", "GCP"]], experience_min_months: null, experience_max_months: null, active: true,
  members: 12, unavailable: [], created_by: null, updated_at: "2026-10-09T10:00:00Z", ...over,
});
const card = {
  id: "c1", candidate_code: "CAN-000001", name: "Rahul Kumar", preferred_role: "Cloud Engineer", current_company: null, experience_months: 24,
  location: "Pune", notice_days: 15, expected_salary: null, source: { id: "s1", name: "Referral", active: true }, source_detail: null, status: "available",
  skills: [{ name: "AWS", level: "advanced", status: "claimed", matched: true }],
};
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  push.mockReset();
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("rule helpers", () => {
  it("summarises a rule in plain words", () => {
    expect(ruleText(pool())).toBe("AWS, Azure or GCP");
    expect(ruleText(pool({ all: ["Java", "Spring"], any: [["AWS", "Azure"]], experience_min_months: 24 }))).toBe("Java and Spring · AWS or Azure · 2+ years of experience");
    expect(ruleText(pool({ any: [], experience_max_months: 11 }))).toBe("Under 1 year of experience"); // AC2: Freshers
    expect(ruleText(pool({ any: [], experience_min_months: 12 }))).toBe("1+ year of experience");
    expect(ruleText(pool({ any: [], experience_min_months: 24, experience_max_months: 59 }))).toBe("2–4 years of experience");
  });

  it("maps whole years to months and back (a maximum year covers the whole year)", () => {
    const form = { name: " Freshers ", all: [" Java ", "java"], any: [[], ["AWS"]], expMin: "", expMax: "0", active: false };
    expect(poolBody(form, false)).toEqual({ name: "Freshers", all: ["Java"], any: [["AWS"]], experience_min_months: null, experience_max_months: 11 });
    expect(poolBody(form, true).active).toBe(false);
    expect(formOf(pool({ experience_min_months: 12, experience_max_months: 59 }))).toMatchObject({ expMin: "1", expMax: "4" });
  });

  it("links a skill pool to Find Candidates, and not a pool without skills", () => {
    expect(findHref(pool())).toBe("/recruiter/find-candidates?any1=AWS&any1=Azure&any1=GCP");
    expect(findHref(pool({ any: [], experience_max_months: 11 }))).toBeNull();
  });

  it("leaves skills no longer in the Skills Master out of the Find Candidates link (QA-03)", () => {
    expect(findHref(pool({ unavailable: ["GCP"] }))).toBe("/recruiter/find-candidates?any1=AWS&any1=Azure");
    expect(findHref(pool({ all: ["Java"], unavailable: ["Java"] }))).toBeNull(); // the pool matches nobody: nothing to refine
    expect(findHref(pool({ any: [["GCP"]], unavailable: ["GCP"] }))).toBeNull();
  });
});

describe("RecruiterTalentPools", () => {
  it("lists the pools with counts and flags; a recruiter gets no New pool", async () => {
    fetchMock.mockResolvedValue(res({ items: [pool(), pool({ id: "p2", name: "Java Developers", all: ["Java"], any: [], members: 1, unavailable: ["Java"] })], can_manage: false }));
    render(<RecruiterTalentPools />);
    expect(await screen.findByRole("link", { name: "Cloud Engineers" })).toHaveAttribute("href", "/recruiter/pools/p1");
    expect(screen.getByText("12 candidates")).toBeInTheDocument();
    expect(screen.getByText("1 candidate")).toBeInTheDocument();
    expect(screen.getByText("Needs attention")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "+ New pool" })).not.toBeInTheDocument();
  });

  it("shows an empty state and a retryable error", async () => {
    fetchMock.mockResolvedValueOnce(res({ detail: "boom" }, 500)).mockResolvedValueOnce(res({ items: [], can_manage: false }));
    render(<RecruiterTalentPools />);
    fireEvent.click(await screen.findByRole("button", { name: "Try again" }));
    expect(await screen.findByText("No talent pools yet.")).toBeInTheDocument();
    expect(screen.getByText("Your placement manager creates the pools.")).toBeInTheDocument();
  });

  it("lets a manager create a pool, adding a typed skill, and opens it", async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) =>
      Promise.resolve(init?.method === "POST" ? res(pool({ id: "p9", name: "Cloud" }), 201) : res({ items: [], can_manage: true })));
    render(<RecruiterTalentPools />);
    fireEvent.click(await screen.findByRole("button", { name: "+ New pool" }));
    fireEvent.change(screen.getByLabelText("Pool name"), { target: { value: "Cloud" } });
    fireEvent.click(screen.getByRole("button", { name: "+ Add an “at least one of” group" }));
    fireEvent.change(screen.getByLabelText("And at least one of these (group 1)"), { target: { value: "AWS" } });
    fireEvent.click(screen.getByRole("button", { name: "Create pool" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/recruiter/pools/p9"));
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST")!;
    expect(JSON.parse(post[1].body)).toEqual({ name: "Cloud", all: [], any: [["AWS"]], experience_min_months: null, experience_max_months: null });
  });

  it("shows the API's unknown-skill message and keeps the form", async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) =>
      Promise.resolve(init?.method === "POST"
        ? res({ detail: { message: "No skill is called “Jav”. Did you mean Java?", code: "unknown_skill", term: "Jav", suggestions: ["Java"] } }, 422)
        : res({ items: [], can_manage: true })));
    render(<RecruiterTalentPools />);
    fireEvent.click(await screen.findByRole("button", { name: "+ New pool" }));
    fireEvent.change(screen.getByLabelText("Pool name"), { target: { value: "Java" } });
    fireEvent.change(screen.getByLabelText("Must have all of these skills"), { target: { value: "Jav" } });
    fireEvent.click(screen.getByRole("button", { name: "Create pool" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("No skill is called “Jav”. Did you mean Java?");
    expect(screen.getByLabelText("Pool name")).toHaveValue("Java");
    expect(push).not.toHaveBeenCalled();
  });

  it("checks the name and the years before sending", async () => {
    fetchMock.mockResolvedValue(res({ items: [], can_manage: true }));
    render(<RecruiterTalentPools />);
    fireEvent.click(await screen.findByRole("button", { name: "+ New pool" }));
    fireEvent.click(screen.getByRole("button", { name: "Create pool" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Enter a pool name.");
    fireEvent.change(screen.getByLabelText("Pool name"), { target: { value: "Mid" } });
    fireEvent.change(screen.getByLabelText("Experience from (years)"), { target: { value: "5" } });
    fireEvent.change(screen.getByLabelText("Experience to (years)"), { target: { value: "2" } });
    fireEvent.click(screen.getByRole("button", { name: "Create pool" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The minimum experience cannot be above the maximum.");
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(0);
  });
});

describe("RecruiterTalentPool", () => {
  const members = (over: Partial<Pool> = {}, can_manage = false, total = 1) =>
    res({ pool: pool({ members: total, ...over }), items: total ? [card] : [], total, limit: 50, offset: 0, terms: [], can_manage });

  it("shows the rule, the members and the Find Candidates link; no Edit for a recruiter", async () => {
    fetchMock.mockResolvedValue(members());
    render(<RecruiterTalentPool poolId="p1" />);
    expect(await screen.findByRole("heading", { name: "Cloud Engineers" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "1 candidate" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Rahul Kumar" })).toHaveAttribute("href", "/recruiter/candidates/c1");
    expect(screen.getByRole("link", { name: "Refine in Find Candidates" })).toHaveAttribute("href", "/recruiter/find-candidates?any1=AWS&any1=Azure&any1=GCP");
    expect(screen.queryByRole("button", { name: "Edit pool" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Shortlist/ })).not.toBeInTheDocument();
    expect(screen.getByText("(matches this pool)")).toBeInTheDocument(); // QA-01: not "your search"
  });

  it("warns about skills no longer in the Skills Master (P5) and explains an empty pool", async () => {
    fetchMock.mockResolvedValue(members({ unavailable: ["AWS"] }, false, 0));
    render(<RecruiterTalentPool poolId="p1" />);
    expect(await screen.findByText("Some skills in this pool are no longer in the Skills Master: AWS.")).toBeInTheDocument();
    expect(screen.getByText(/Ask your placement manager to update it/)).toBeInTheDocument();
    expect(screen.getByText(/No candidates match this pool yet/)).toBeInTheDocument();
  });

  it("lets a manager edit the pool and reloads the members", async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) =>
      Promise.resolve(init?.method === "PATCH" ? res(pool({ name: "Cloud Pros" })) : members({}, true)));
    render(<RecruiterTalentPool poolId="p1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit pool" }));
    fireEvent.change(screen.getByLabelText("Pool name"), { target: { value: "Cloud Pros" } });
    fireEvent.click(screen.getByLabelText(/Active/));
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Pool saved. Members are recalculated from the new rule.")).toBeInTheDocument();
    const patch = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH")!;
    expect(patch[0]).toBe("/api/v1/recruiter/pools/p1");
    expect(JSON.parse(patch[1].body)).toMatchObject({ name: "Cloud Pros", active: false, any: [["AWS", "Azure", "GCP"]] });
    expect(fetchMock.mock.calls.filter(([u]) => String(u).includes("/candidates?")).length).toBeGreaterThanOrEqual(2);
    await waitFor(() => expect(screen.getByRole("button", { name: "Edit pool" })).toHaveFocus()); // QA-02
  });

  it("returns focus to Edit pool on Cancel (QA-02)", async () => {
    fetchMock.mockResolvedValue(members({}, true));
    render(<RecruiterTalentPool poolId="p1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit pool" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Edit pool" })).toHaveFocus());
  });

  it("shows a not-found pool without a retry", async () => {
    fetchMock.mockResolvedValue(res({ detail: "Talent pool not found" }, 404));
    render(<RecruiterTalentPool poolId="nope" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Talent pool not found");
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Back to talent pools/ })).not.toBeInTheDocument(); // QA-04: the page frame has it
  });
});
