import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RequirementSourcing from "@/components/RequirementSourcing";
import { bodyOf, draftOf, searchHref, type Sourcing } from "@/lib/requirementSourcing";

// pob-017 (DEC-SCOPE-429): the sourcing plan card. The server decides every rule; these check what is shown, what is sent and how a failure reads.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const URL = "/api/v1/recruiter/requirements/R1/sourcing";
const zero = { found: 0, screened: 0, suitable: 0, submitted: 0, rejected: 0, conversion: null };

const sourcing = (over: Partial<Sourcing> = {}): Sourcing => ({
  plan: {
    target_profile: "Java backend, Pune", boolean_strings: [{ label: "Naukri", query: '"java" AND kafka' }], target_found: 10, target_screened: null, target_submitted: 2,
    deadline: "2026-11-01", source_owner: { id: "U1", full_name: "Asha Rao", active: true }, updated_by: { id: "U1", full_name: "Asha Rao", active: true },
    updated_at: "2026-11-08T05:00:00Z",
  },
  channels: [{ id: "S1", name: "LinkedIn", active: true }],
  searches: [{ id: "Q1", name: "Java Pune", filters: { all: ["Java"] }, ignored: [], shared: false, mine: true, can_edit: true, owner: { id: "U1", name: "Asha Rao" } }],
  hidden_searches: 1,
  funnel: {
    rows: [
      { source: { id: "S1", name: "LinkedIn", active: true }, planned: true, found: 3, screened: 2, suitable: 2, submitted: 1, rejected: 0, conversion: 1 / 3 },
      { source: { id: "S2", name: "Referral", active: true }, planned: false, found: 1, screened: 1, suitable: 0, submitted: 0, rejected: 1, conversion: 0 },
    ],
    total: { found: 4, screened: 3, suitable: 2, submitted: 1, rejected: 1, conversion: 0.25 },
  },
  progress: { state: "breached", short: ["found", "submitted"], deadline: "2026-11-01", days_left: -7, found: { actual: 4, target: 10 }, screened: { actual: 3, target: null }, submitted: { actual: 1, target: 2 } },
  can_edit: true, can_link_searches: true,
  ...over,
});

let calls: { url: string; method: string; body: unknown }[];
let answer: (url: string, method: string) => Response;

beforeEach(() => {
  calls = [];
  answer = (url) => (url.includes("catalogue") ? res({ items: [{ id: "S1", name: "LinkedIn", active: true, sort_order: 1 }, { id: "S2", name: "Referral", active: true, sort_order: 2 }], total: 2, limit: 200, offset: 0 })
    : url.includes("saved-searches") ? res({ items: sourcing().searches }) : res(sourcing()));
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    return answer(url, method);
  }));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const team = [{ id: "U1", full_name: "Asha Rao" }, { id: "U2", full_name: "Vikram Iyer" }];
const skills = [{ name: "Java", kind: "required" }, { name: "Kafka", kind: "preferred" }];
const show = async () => {
  render(<RequirementSourcing requirementId="R1" version="v1" team={team} skills={skills} />);
  await screen.findByRole("table", { name: "Candidates by source" });
};

describe("the sourcing plan card", () => {
  it("shows a loading state, then the plan, the breach and the funnel with its total", async () => {
    render(<RequirementSourcing requirementId="R1" version="v1" team={team} skills={skills} />);
    expect(screen.getByText("Loading the sourcing plan…")).toBeTruthy();
    await screen.findByRole("table", { name: "Candidates by source" });
    expect(screen.getByText("Deadline missed")).toBeTruthy();
    expect(screen.getByText(/these are short: profiles to find, profiles to submit/)).toBeTruthy();
    expect(screen.getByText("Java")).toBeTruthy();
    expect(screen.getByText("Kafka")).toBeTruthy();
    const total = within(screen.getByRole("rowheader", { name: "Total" }).closest("tr") as HTMLElement);
    expect(total.getByText("25%")).toBeTruthy();
    expect(screen.getByText("1 more you cannot see (private to their owner)")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Java Pune" }).getAttribute("href")).toContain("/recruiter/find-candidates?");
  });

  it("copies a search string", async () => {
    const writeText = vi.fn(async () => undefined);
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
    await show();
    fireEvent.click(screen.getByRole("button", { name: "Copy Naukri" }));
    await screen.findByText("Copied “Naukri”.");
    expect(writeText).toHaveBeenCalledWith('"java" AND kafka');
  });

  it("says when nothing is found yet and no plan exists", async () => {
    answer = () => res(sourcing({ plan: { ...sourcing().plan, target_profile: null, boolean_strings: [], updated_at: null, source_owner: null },
      channels: [], searches: [], hidden_searches: 0, funnel: { rows: [], total: zero },
      progress: { state: "no_targets", short: [], deadline: null, days_left: null, found: { actual: 0, target: null }, screened: { actual: 0, target: null }, submitted: { actual: 0, target: null } } }));
    render(<RequirementSourcing requirementId="R1" version="v1" team={team} skills={[]} />);
    await screen.findByText("No candidates on this requirement yet, and no channels planned.");
    expect(screen.getByRole("button", { name: "Create plan" })).toBeTruthy();
    expect(screen.getByText("No targets set")).toBeTruthy();
  });

  it("edits and saves the whole plan", async () => {
    await show();
    fireEvent.click(screen.getByRole("button", { name: "Edit plan" }));
    await screen.findByRole("checkbox", { name: "Referral" });
    fireEvent.click(screen.getByRole("checkbox", { name: "Referral" }));
    fireEvent.change(screen.getByLabelText("Profiles to screen"), { target: { value: "5" } });
    fireEvent.change(screen.getByLabelText("Source owner"), { target: { value: "U2" } });
    fireEvent.click(screen.getByRole("button", { name: "Save plan" }));
    await screen.findByText("Sourcing plan saved.");
    const put = calls.find((c) => c.method === "PUT");
    expect(put?.url).toBe(URL);
    expect(put?.body).toMatchObject({ channel_ids: ["S1", "S2"], target_screened: 5, source_owner_user_id: "U2", saved_search_ids: ["Q1"], target_found: 10 });
  });

  it("shows the API's refusal and keeps the form", async () => {
    await show();
    fireEvent.click(screen.getByRole("button", { name: "Edit plan" }));
    answer = (url, method) => (method === "PUT" ? res({ detail: "The source owner must be one of this requirement's owners" }, 422) : res({ items: [] }));
    fireEvent.click(screen.getByRole("button", { name: "Save plan" }));
    expect((await screen.findByRole("alert")).textContent).toContain("source owner must be one of");
    expect(screen.getByRole("button", { name: "Save plan" })).toBeTruthy();
  });

  it("hides editing for a reader", async () => {
    answer = () => res(sourcing({ can_edit: false }));
    await show();
    expect(screen.queryByRole("button", { name: "Edit plan" })).toBeNull();
  });

  it("offers a retry when the plan cannot be read", async () => {
    answer = () => res({ detail: "Job requirement not found" }, 404);
    render(<RequirementSourcing requirementId="R1" version="v1" team={team} skills={[]} />);
    expect((await screen.findByRole("alert")).textContent).toContain("not found");
    answer = () => res(sourcing());
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.getByRole("table", { name: "Candidates by source" })).toBeTruthy());
  });
});

describe("the plan body", () => {
  it("drops empty search-string rows, refuses half rows and non-numbers", () => {
    const draft = draftOf(sourcing());
    expect(bodyOf({ ...draft, boolean_strings: [...draft.boolean_strings, { label: " ", query: "" }] })).toMatchObject({ body: { boolean_strings: [{ label: "Naukri" }] } });
    expect(bodyOf({ ...draft, boolean_strings: [{ label: "x", query: "" }] })).toEqual({ error: "Give each search string both a name and the string itself." });
    expect(bodyOf({ ...draft, target_found: "2.5" })).toEqual({ error: "Profiles to find: enter a whole number." });
    expect(bodyOf({ ...draft, target_found: "", deadline: "" })).toMatchObject({ body: { target_found: null, deadline: null } });
  });

  it("links a saved search to Find Candidates with its filters", () => {
    expect(searchHref(sourcing().searches[0])).toMatch(/^\/recruiter\/find-candidates\?.*Java/);
  });
});
