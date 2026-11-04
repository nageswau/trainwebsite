import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import RecruiterRequirementDetail from "@/components/RecruiterRequirementDetail";
import RecruiterRequirementMatches from "@/components/RecruiterRequirementMatches";
import RecruiterSkillsPanel from "@/components/RecruiterSkillsPanel";
import { minLevelText, type Matches } from "@/lib/recruiterMatching";
import type { Requirement } from "@/lib/recruiterRequirements";
import { skillsQuery } from "@/lib/recruiterSkills";

// hrc-017 (DEC-SCOPE-386 T4, T6, T9): category domains in the Skills Master, the domain filter, and a requirement skill's minimum level.
const nav = vi.hoisted(() => ({ params: new URLSearchParams(), push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: nav.push, refresh: vi.fn(), replace: vi.fn() }), usePathname: () => "/recruiter/manager/skills", useSearchParams: () => nav.params }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const page = (items: unknown[]) => ({ items, total: items.length, limit: 50, offset: 0 });
const programming = { id: "c1", name: "Programming", active: true, sort_order: 1, domain: "it" };
const pharmacy = { id: "c7", name: "Pharmacy", active: true, sort_order: 8, domain: "non_it" };
const pv = { id: "s9", name: "Pharmacovigilance", active: true, category: { id: "c7", name: "Pharmacy", active: true }, tags: [], aliases: [], related: [] };

type Call = { url: string; init?: RequestInit };
function serve(handler: (call: Call) => Response | undefined = () => undefined) {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const call = { url: String(url), init };
    calls.push(call);
    const handled = handler(call);
    if (handled) return Promise.resolve(handled);
    if (call.url.includes("/skill-categories")) return Promise.resolve(res(page([programming, pharmacy])));
    if (call.url.includes("/matches")) return Promise.resolve(res(matches()));
    return Promise.resolve(res(page([pv])));
  }));
  return calls;
}
const sentBody = (calls: Call[], method: string) => calls.filter((c) => c.init?.method === method).map((c) => JSON.parse(String(c.init!.body)));

function matches(): Matches {
  return {
    criteria: {
      skills: [
        { id: "S1", name: "Python", kind: "required", weight: 2, points: 90, in_master: true, min_level: "intermediate" },
        { id: "S2", name: "AWS", kind: "preferred", weight: 1, points: 0, in_master: true, min_level: null },
        { id: "S3", name: "Weblogic", kind: "required", weight: 2, points: 0, in_master: false, min_level: null },
      ],
      experience: null, location: null,
    },
    reason: null, items: [], total: 0, limit: 20, offset: 0, can_shortlist: true, can_edit_weights: true,
  };
}

afterEach(() => {
  cleanup();
  nav.params = new URLSearchParams();
  nav.push.mockReset();
  vi.unstubAllGlobals();
});

describe("Skills Master domains (hrc-017)", () => {
  it("adds a non-IT category and shows each category's domain", async () => {
    const calls = serve(({ url, init }) => (init?.method === "POST" && url.endsWith("/skill-categories") ? res({ ...pharmacy, id: "c8", name: "Retail" }, 201) : undefined));
    render(<RecruiterSkillsPanel canEdit />);
    const list = await screen.findByRole("region", { name: "Category list" });
    expect(within(within(list).getByText("Pharmacy").closest("tr")!).getByText("Non-IT")).toBeInTheDocument();
    expect(within(within(list).getByText("Programming").closest("tr")!).getByText("IT")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Category name (required)"), { target: { value: "Retail" } });
    fireEvent.change(screen.getByLabelText("Domain of the new category"), { target: { value: "non_it" } });
    fireEvent.click(screen.getByRole("button", { name: "Add category" }));
    expect(await screen.findByText("Added category Retail.")).toBeInTheDocument();
    expect(sentBody(calls, "POST")).toEqual([{ name: "Retail", domain: "non_it" }]);
  });

  it("moves a category to the other domain", async () => {
    const calls = serve(({ init }) => (init?.method === "PATCH" ? res({ ...programming, domain: "non_it" }) : undefined));
    render(<RecruiterSkillsPanel canEdit />);
    fireEvent.click(await screen.findByRole("button", { name: "Move Programming to Non-IT" }));
    expect(await screen.findByText("Moved Programming to Non-IT.")).toBeInTheDocument();
    expect(calls.find((c) => c.init?.method === "PATCH")!.url).toMatch(/\/skill-categories\/c1$/);
    expect(sentBody(calls, "PATCH")).toEqual([{ domain: "non_it" }]);
  });

  it("filters the skills by domain through the URL", async () => {
    const calls = serve();
    nav.params = new URLSearchParams("domain=non_it");
    render(<RecruiterSkillsPanel canEdit={false} />);
    await screen.findByText("Pharmacovigilance");
    expect(calls.some((c) => c.url.includes("/skills?limit=50&offset=0&domain=non_it"))).toBe(true);
    const domain = screen.getByLabelText("Domain") as HTMLSelectElement;
    expect(domain.value).toBe("non_it");
    fireEvent.change(domain, { target: { value: "it" } });
    fireEvent.submit(domain.closest("form")!);
    expect(nav.push).toHaveBeenCalledWith("/recruiter/manager/skills?domain=it", { scroll: false });
  });

  it("ignores a hand-edited domain that is not IT or non-IT", () => {
    expect(skillsQuery({ q: "", category: "", domain: "x", offset: 0 }, 50)).toBe("limit=50&offset=0");
  });
});

describe("Requirement skill minimum level (hrc-017)", () => {
  it("labels a level and no level", () => {
    expect(minLevelText("intermediate")).toBe("Intermediate or above");
    expect(minLevelText(null)).toBe("");
    expect(minLevelText(undefined)).toBe("");
  });

  it("shows the level in the scoring line", async () => {
    serve();
    render(<RecruiterRequirementMatches requirementId="J1" />);
    expect(await screen.findByText(/Python \(Intermediate or above\) 90/)).toBeInTheDocument();
  });

  it("sets a minimum level on Skills Master skills only and sends only the changed levels", async () => {
    const calls = serve(({ init }) => (init?.method === "PUT" ? res({ requirement: { id: "J1", code: "REQ-000001", skills: [] } }) : undefined));
    render(<RecruiterRequirementMatches requirementId="J1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Adjust weights" }));
    const python = screen.getByLabelText("Minimum level of Python (required)") as HTMLSelectElement;
    expect(python.value).toBe("intermediate");
    expect(screen.queryByLabelText("Minimum level of Weblogic (required)")).toBeNull();
    // QA-01: a free-text skill's cell has no level select -- the grid must not stretch its weight input to the row height
    expect((python.closest("div.field")!.parentElement as HTMLElement).style.alignItems).toBe("start");
    fireEvent.change(screen.getByLabelText("Minimum level of AWS (preferred)"), { target: { value: "advanced" } });
    fireEvent.click(screen.getByRole("button", { name: "Save weights" }));
    await waitFor(() => expect(sentBody(calls, "PUT")).toHaveLength(1));
    expect(sentBody(calls, "PUT")[0]).toEqual({ weights: [{ id: "S1", weight: 2 }, { id: "S2", weight: 1, min_level: "advanced" }, { id: "S3", weight: 2 }] });
  });

  it("clears a level with Any level", async () => {
    const calls = serve(({ init }) => (init?.method === "PUT" ? res({ requirement: { id: "J1", code: "REQ-000001", skills: [] } }) : undefined));
    render(<RecruiterRequirementMatches requirementId="J1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Adjust weights" }));
    fireEvent.change(screen.getByLabelText("Minimum level of Python (required)"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save weights" }));
    await waitFor(() => expect(sentBody(calls, "PUT")).toHaveLength(1));
    expect(sentBody(calls, "PUT")[0].weights[0]).toEqual({ id: "S1", weight: 2, min_level: null });
  });
});

describe("Requirement detail skill levels (hrc-017)", () => {
  it("lists a skill's minimum level next to its name", () => {
    serve();
    const requirement = {
      id: "R1", code: "REQ-0001", title: "Python Dev", company: { id: "C1", code: "CO-1", name: "Acme" }, location: "Pune", status: "new", status_label: "New",
      phase: "draft", phase_label: "Draft", source: "recruiter", priority: null, vacancies: 1, closes_on: null, requirement_date: null, deadline_state: null,
      assigned_recruiter: null, permissions: { can_edit: false, can_change_status: false, can_reassign: false, can_view_matches: false, can_manage_owners: false,
        can_view_candidates: false }, owners: [], description: "", department: null, job_category: null, qualification: null, experience_min_months: null,
      experience_max_months: null, salary_min: null, salary_max: null, work_mode: null, shift: null, employment_type: null, joining_requirement: null,
      skills: [
        { id: "S1", name: "Python", kind: "required", weight: 2, skill_id: "k1", matched: true, min_level: "intermediate" },
        { id: "S2", name: "AWS", kind: "preferred", weight: 1, skill_id: "k2", matched: true, min_level: null },
      ],
      joined_count: 0, allowed_statuses: [], status_history: [], created_by: null, created_at: "2026-11-01T00:00:00Z", updated_at: "2026-11-04T04:00:00Z",
      approval: { required: false, submitted_by: null, submitted_at: null, can_submit: false, can_decide: false },
      visibility: { key: "public", label: "Public website", segment_pool: null, can_change: false },
    } as unknown as Requirement;
    render(<RecruiterRequirementDetail initial={requirement} initialJd={null} />);
    expect(screen.getByText("Python").closest("li")!.textContent).toBe("Python · Intermediate or above");
    expect(screen.getByText("AWS").closest("li")!.textContent).toBe("AWS");
  });
});
