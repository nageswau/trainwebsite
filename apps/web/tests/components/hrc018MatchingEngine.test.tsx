import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterMatchSettings from "@/components/RecruiterMatchSettings";
import RecruiterRequirementMatches from "@/components/RecruiterRequirementMatches";
import type { Matches, MatchSettings } from "@/lib/recruiterMatching";

// hrc-018 (DEC-SCOPE-392; AC1, AC3): the factor criteria, the disclaimer, each row's explanation, the hard filters in "Adjust weights",
// and the super_admin's match weights card (the total must be 100).
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const DEFAULTS = { skills: 40, experience: 20, qualification: 15, location: 10, role: 10, salary: 5 };
const off = { on: false, available: false };

const matches = (): Matches => ({
  criteria: {
    skills: [{ id: "S1", name: "Java", kind: "required", weight: 2, points: 57, in_master: true }],
    experience: { min_months: 24, max_months: null, points: 29 },
    location: null,
    factors: [
      { key: "skills", label: "Skills", weight: 40, applies: true, points: 57 },
      { key: "experience", label: "Experience", weight: 20, applies: true, points: 29 },
      { key: "qualification", label: "Qualification", weight: 15, applies: false, points: 0 },
      { key: "location", label: "Location", weight: 10, applies: false, points: 0 },
      { key: "role", label: "Role", weight: 10, applies: true, points: 14 },
      { key: "salary", label: "Salary & availability", weight: 5, applies: false, points: 0 },
    ],
    hard_filters: { experience: { on: true, available: true }, qualification: off, location: off, salary: off },
  },
  reason: null,
  disclaimer: "A match score is a guide based on the details recorded on the profile and the requirement. It is not a guarantee of suitability, an interview or an offer.",
  items: [{
    id: "C1", candidate_code: "CAN-000001", name: "Rahul Kumar", preferred_role: "Java Developer", current_company: null, experience_months: 36,
    location: "Pune", notice_days: 30, status: "available", score: 100, application: null,
    breakdown: [{ key: "skill:S1", label: "Java", kind: "required", points: 57, max: 57, matched: true }],
    explanation: [
      { key: "skills", label: "Skills", text: "Matches 1 of 1 required skills", points: 57, max: 57, matched: true },
      { key: "experience", label: "Experience", text: "3 yrs relevant (needs 2+ yrs)", points: 29, max: 29, matched: true },
      { key: "role", label: "Role", text: "Wants a Java Developer role", points: 14, max: 14, matched: true },
    ],
  }],
  total: 1, limit: 20, offset: 0, can_shortlist: true, can_edit_weights: true,
});

let settings: MatchSettings;
let putReply: (body: unknown) => Response;
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  settings = { weights: { ...DEFAULTS }, defaults: { ...DEFAULTS }, can_edit: true };
  putReply = () => res({ requirement: { id: "J1", code: "REQ-000001", skills: [] } });
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "PUT") return Promise.resolve(putReply(JSON.parse(String(init.body))));
    if (url.startsWith("/api/v1/recruiter/requirements/J1/matches")) return Promise.resolve(res(matches()));
    if (url === "/api/v1/recruiter/match-settings") return Promise.resolve(res(settings));
    return Promise.resolve(res({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
const sent = () => fetchMock.mock.calls.filter(([, init]) => init?.method === "PUT").map(([url, init]) => [url, JSON.parse(init.body)]);

describe("RecruiterRequirementMatches (hrc-018)", () => {
  it("shows the factor points, the hard filters, the disclaimer and why each candidate matches", async () => {
    render(<RecruiterRequirementMatches requirementId="J1" />);
    expect(await screen.findByText(/Score out of 100: Java 57 · Experience 29 · Role 14\. Candidates must have every required skill and meet: minimum experience\./)).toBeTruthy();
    expect(screen.getByText(/It is not a guarantee/)).toBeTruthy();
    const why = screen.getByRole("list", { name: "Why Rahul Kumar matches" });
    expect(within(why).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Skills (57 of 57) Matches 1 of 1 required skills", "Experience (29 of 29) 3 yrs relevant (needs 2+ yrs)", "Role (14 of 14) Wants a Java Developer role",
    ]);
  });

  it("QA-02: with an explanation, the chips keep only the per-skill detail (the factors are not shown twice)", async () => {
    const withFactor = matches();
    withFactor.items[0].breakdown.push({ key: "experience", label: "Experience", kind: "experience", points: 29, max: 29, matched: true });
    fetchMock.mockImplementation((url: string) => Promise.resolve(res(url.includes("/matches") ? withFactor : settings)));
    render(<RecruiterRequirementMatches requirementId="J1" />);
    const chips = await screen.findByRole("list", { name: "Score breakdown for Rahul Kumar" });
    expect(within(chips).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["Java: 57 of 57 (matched)"]);
  });

  it("sends only the hard filters that changed and explains the ones the requirement cannot use", async () => {
    render(<RecruiterRequirementMatches requirementId="J1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Adjust weights" }));
    const experience = screen.getByRole("checkbox", { name: "Minimum experience" }) as HTMLInputElement;
    const salary = screen.getByRole("checkbox", { name: /Within the maximum salary/ }) as HTMLInputElement;
    expect(experience.checked).toBe(true);
    expect(salary.disabled).toBe(true);
    expect(screen.getByText("Set a maximum salary on the requirement first.")).toBeTruthy();
    fireEvent.click(experience);
    fireEvent.click(screen.getByRole("button", { name: "Save weights" }));
    await waitFor(() => expect(sent()).toHaveLength(1));
    expect(sent()[0]).toEqual(["/api/v1/recruiter/requirements/J1/skill-weights", { weights: [{ id: "S1", weight: 2 }], hard_filters: { experience: false } }]);
  });

  it("leaves hard_filters out when no switch changed", async () => {
    render(<RecruiterRequirementMatches requirementId="J1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Adjust weights" }));
    fireEvent.click(screen.getByRole("button", { name: "Save weights" }));
    await waitFor(() => expect(sent()).toHaveLength(1));
    expect(sent()[0][1]).toEqual({ weights: [{ id: "S1", weight: 2 }] });
  });
});

describe("RecruiterMatchSettings", () => {
  it("is hidden from who cannot change the weights", async () => {
    settings.can_edit = false;
    const { container } = render(<RecruiterMatchSettings />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(container.textContent).toBe("");
  });

  it("offers Save only when the weights add up to 100, then saves them", async () => {
    putReply = (body) => res({ weights: (body as { weights: MatchSettings["weights"] }).weights, defaults: DEFAULTS, can_edit: true });
    render(<RecruiterMatchSettings />);
    const skills = (await screen.findByLabelText("Skills")) as HTMLInputElement;
    const save = screen.getByRole("button", { name: "Save weights" }) as HTMLButtonElement;
    expect(screen.getByText("Total 100 of 100.")).toBeTruthy();
    fireEvent.change(skills, { target: { value: "45" } });
    expect(screen.getByText("Total 105 of 100 — the weights must add up to 100.")).toBeTruthy();
    expect(save.disabled).toBe(true);
    fireEvent.change(skills, { target: { value: "4.5" } });
    expect(screen.getByText("Each weight must be a whole number from 0 to 100.")).toBeTruthy();
    fireEvent.change(skills, { target: { value: "35" } });
    fireEvent.change(screen.getByLabelText("Role"), { target: { value: "15" } });
    expect(save.disabled).toBe(false);
    fireEvent.click(save);
    expect(await screen.findByText("Match weights saved. Every requirement's matches now use them.")).toBeTruthy();
    expect(sent()).toEqual([["/api/v1/recruiter/match-settings", { weights: { ...DEFAULTS, skills: 35, role: 15 } }]]);
  });

  it("shows the server's refusal and can restore the defaults", async () => {
    settings.weights = { ...DEFAULTS, skills: 30, role: 20 };
    putReply = () => res({ detail: "Only a super admin can change the match weights" }, 403);
    render(<RecruiterMatchSettings />);
    expect(((await screen.findByLabelText("Skills")) as HTMLInputElement).value).toBe("30");
    fireEvent.click(screen.getByRole("button", { name: "Use the defaults" }));
    expect((screen.getByLabelText("Skills") as HTMLInputElement).value).toBe("40");
    fireEvent.click(screen.getByRole("button", { name: "Save weights" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Only a super admin can change the match weights");
  });
});
