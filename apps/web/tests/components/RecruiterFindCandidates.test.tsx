import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterFindCandidates from "@/components/RecruiterFindCandidates";

// rec-013 (spec §5): the search lives in the URL; the form edits a draft that Search or a facet pushes. hr_team (writes=false) gets no
// Shortlist / Contact and never calls the recruiter catalogue.
let query = "";
const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }), usePathname: () => "/recruiter/find-candidates", useSearchParams: () => new URLSearchParams(query),
}));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const card = {
  id: "c1", candidate_code: "CAN-000001", name: "Rahul Kumar", preferred_role: "Java Developer", current_company: "Acme", experience_months: 36,
  location: "Hyderabad", notice_days: 0, expected_salary: "800000.00", source: { id: "s2", name: "Edusphere students", active: true },
  source_detail: "Java Full Stack", status: "available",
  skills: [{ name: "Java", level: "advanced", status: "verified", matched: true }, { name: "SQL", level: "beginner", status: "claimed", matched: false }],
};
const result = {
  items: [card], total: 87, limit: 50, offset: 0,
  facets: {
    experience: [{ key: "y0_1", count: 10 }, { key: "y1_3", count: 40 }, { key: "y3_5", count: 30 }, { key: "y5_plus", count: 5 }, { key: "none", count: 2 }],
    location: [{ value: "Hyderabad", count: 80 }, { value: "__other__", count: 5 }, { value: null, count: 2 }],
    availability: [{ key: "immediate", count: 50 }, { key: "d15", count: 10 }, { key: "d30", count: 10 }, { key: "d31_59", count: 5 }, { key: "d60_plus", count: 10 }, { key: "none", count: 2 }],
  },
  terms: [{ term: "j2ee", skill: { id: "k1", name: "Java" }, also: ["Core Java"] }],
};
let fetchMock: ReturnType<typeof vi.fn>;
let searchReply: () => Response;

beforeEach(() => {
  query = "";
  push.mockReset();
  searchReply = () => res(result);
  fetchMock = vi.fn((url: string) => {
    if (url.startsWith("/api/v1/recruiter/catalogue/candidate-sources")) return Promise.resolve(res({ items: [], total: 0, limit: 100, offset: 0 }));
    return Promise.resolve(searchReply());
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const searchCalls = () => fetchMock.mock.calls.filter(([u]) => String(u).startsWith("/api/v1/recruiter/candidates/search"));

describe("RecruiterFindCandidates", () => {
  it("asks for a skill first and sends nothing", () => {
    render(<RecruiterFindCandidates writes sourceFilter />);
    expect(screen.getByText("Add at least one skill to search every candidate in the pool.")).toBeInTheDocument();
    expect(searchCalls()).toHaveLength(0);
  });

  it("searches the URL's skills and shows the count, what each term matched, the card and the facets", async () => {
    query = "all=j2ee&any1=AWS&any1=Azure&exp_min=2&exp_max=5";
    render(<RecruiterFindCandidates writes sourceFilter />);
    expect(await screen.findByRole("heading", { name: "87 candidates found" })).toBeInTheDocument();
    const [url, init] = searchCalls()[0];
    expect(url).toBe("/api/v1/recruiter/candidates/search?limit=50&offset=0");
    expect(JSON.parse(init.body)).toEqual({ all: ["j2ee"], any: [["AWS", "Azure"]], experience_min_months: 24, experience_max_months: 71 });
    expect(screen.getByText("j2ee → Java, Core Java")).toBeInTheDocument();
    const item = screen.getByRole("listitem", { name: /Rahul Kumar/ });
    expect(within(item).getByText("Java Developer | 3 yr")).toBeInTheDocument();
    expect(within(item).getByText("Immediate")).toBeInTheDocument();
    expect(within(item).getByText("₹8 LPA")).toBeInTheDocument();
    expect(within(item).getByText("Edusphere students — Java Full Stack")).toBeInTheDocument();
    expect(within(item).getByRole("link", { name: "Contact Rahul Kumar" })).toHaveAttribute("href", "/recruiter/candidates/c1#contact");
    expect(within(item).getByRole("button", { name: "Shortlist Rahul Kumar" })).toBeDisabled(); // no requirement chosen yet
    fireEvent.click(screen.getByRole("button", { name: /1–3 years/ }));
    expect(push).toHaveBeenLastCalledWith("/recruiter/find-candidates?all=j2ee&any1=AWS&any1=Azure&exp_min=1&exp_max=2", { scroll: false });
    expect(screen.queryByRole("button", { name: /^Other/ })).toBeNull(); // "Other" is a count, not a filter
  });

  it("adds a chip on Enter, and Search also takes a skill typed but not added", () => {
    render(<RecruiterFindCandidates writes sourceFilter />);
    const box = screen.getByLabelText("Must have all of these skills");
    fireEvent.change(box, { target: { value: "Java" } });
    fireEvent.keyDown(box, { key: "Enter" });
    expect(screen.getByRole("button", { name: "Remove Java" })).toBeInTheDocument();
    fireEvent.change(box, { target: { value: "Spring Boot" } });
    fireEvent.click(screen.getByRole("button", { name: "Search candidates" }));
    expect(push).toHaveBeenLastCalledWith("/recruiter/find-candidates?all=Java&all=Spring+Boot", { scroll: false });
  });

  it("offers the suggestions of an unknown skill and swaps the term in", async () => {
    query = "all=Jav";
    searchReply = () => res({ detail: { message: "No skill is called “Jav”. Did you mean Java?", code: "unknown_skill", term: "Jav", suggestions: ["Java"] } }, 422);
    render(<RecruiterFindCandidates writes sourceFilter />);
    expect(await screen.findByRole("alert")).toHaveTextContent("No skill is called “Jav”. Did you mean Java?");
    fireEvent.click(screen.getByRole("button", { name: "Use Java" }));
    expect(push).toHaveBeenLastCalledWith("/recruiter/find-candidates?all=Java", { scroll: false });
  });

  it("shows a retry when the search fails", async () => {
    query = "all=Java";
    searchReply = () => res({ detail: "boom" }, 500);
    render(<RecruiterFindCandidates writes sourceFilter />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to search candidates.");
    searchReply = () => res(result);
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "87 candidates found" })).toBeInTheDocument();
  });

  it("gives a read-only role no Shortlist, Contact or source picker", async () => {
    query = "all=Java";
    render(<RecruiterFindCandidates writes={false} sourceFilter={false} />);
    const item = await screen.findByRole("listitem", { name: /Rahul Kumar/ });
    expect(within(item).queryByRole("button", { name: /Shortlist/ })).toBeNull();
    expect(within(item).queryByRole("link", { name: /Contact/ })).toBeNull();
    expect(screen.queryByLabelText("Shortlist into requirement")).toBeNull();
    expect(screen.queryByLabelText("Candidate source")).toBeNull();
    expect(fetchMock.mock.calls.some(([u]) => String(u).includes("/catalogue/"))).toBe(false);
  });
});
