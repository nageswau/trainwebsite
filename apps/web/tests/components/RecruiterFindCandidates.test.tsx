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
    availability: [{ key: "immediate", count: 50 }, { key: "d15", count: 10 }, { key: "d30", count: 20 }, { key: "d31_59", count: 0 }, { key: "d60_plus", count: 5 }, { key: "none", count: 2 }],
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
  it("asks for a skill or resume words first and sends nothing", () => {
    render(<RecruiterFindCandidates writes sourceFilter />);
    expect(screen.getByText("Add a skill or a resume search to search every candidate in the pool.")).toBeInTheDocument();
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
    const box = screen.getByRole("textbox", { name: "Must have all of these skills" });
    fireEvent.change(box, { target: { value: "Java" } });
    fireEvent.keyDown(box, { key: "Enter" });
    expect(screen.getByRole("button", { name: "Remove Java" })).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Must have all of these skills: chosen" })).toHaveTextContent("Java");
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

  it("hides empty facet rows (QA-04), and on no results shows neither facets nor the shortlist picker (QA-01)", async () => {
    query = "all=Java";
    render(<RecruiterFindCandidates writes sourceFilter />);
    await screen.findByRole("heading", { name: "87 candidates found" });
    expect(screen.queryByRole("button", { name: /31–59 days/ })).toBeNull();
    expect(screen.queryByText("31–59 days", { selector: "aside *" })).toBeNull();
    cleanup();
    searchReply = () => res({ ...result, items: [], total: 0, facets: { experience: [{ key: "none", count: 0 }], location: [], availability: [{ key: "none", count: 0 }] } });
    render(<RecruiterFindCandidates writes sourceFilter />);
    expect(await screen.findByRole("heading", { name: "0 candidates found" })).toBeInTheDocument();
    expect(screen.getByText("No candidates match. Remove a skill or a filter to see more.")).toBeInTheDocument();
    expect(screen.queryByRole("complementary", { name: "Refine results" })).toBeNull();
    expect(screen.queryByLabelText("Shortlist into requirement")).toBeNull();
  });

  it("offers no Retry for a refused search (QA-02)", async () => {
    query = "all=Java&sal_min=10&sal_max=2";
    searchReply = () => res({ detail: "The minimum salary cannot be above the maximum" }, 422);
    render(<RecruiterFindCandidates writes sourceFilter />);
    expect(await screen.findByText("The minimum salary cannot be above the maximum")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
  });

  it("brings the results into view after a Search (QA-03) and shows that newer results are loading (QA-05)", async () => {
    const scrolled = vi.fn();
    Element.prototype.scrollIntoView = scrolled;
    query = "all=Java";
    const view = render(<RecruiterFindCandidates writes sourceFilter />);
    await screen.findByRole("heading", { name: "87 candidates found" });
    expect(scrolled).not.toHaveBeenCalled(); // opening a link does not jump
    fireEvent.click(screen.getByRole("button", { name: "Search candidates" }));
    let finish: (r: Response) => void = () => undefined;
    searchReply = () => undefined as unknown as Response;
    fetchMock.mockImplementation((url: string) =>
      url.startsWith("/api/v1/recruiter/catalogue/") ? Promise.resolve(res({ items: [], total: 0, limit: 100, offset: 0 })) : new Promise<Response>((r) => { finish = r; }));
    query = "all=Java&location=Pune";
    view.rerender(<RecruiterFindCandidates writes sourceFilter />);
    expect(await screen.findByText("Updating results…")).toBeInTheDocument();
    finish(res({ ...result, total: 3 }));
    expect(await screen.findByRole("heading", { name: "3 candidates found" })).toBeInTheDocument();
    expect(scrolled).toHaveBeenCalled();
  });

  // rec-014 (DEC-SCOPE-152): the resume search box rides in the URL as q, alone or with skills; hits come back as segments, shown in <mark>.
  it("sends the resume search alone and shows the card's resume snippet with its hits marked", async () => {
    query = "q=Microservices+Kafka";
    searchReply = () => res({
      ...result, terms: [], notice: null,
      items: [{ ...card, snippet: [{ text: "Built ", hit: false }, { text: "Microservices", hit: true }, { text: " on <b>Kafka</b>", hit: false }] }],
    });
    render(<RecruiterFindCandidates writes sourceFilter />);
    const item = await screen.findByRole("listitem", { name: /Rahul Kumar/ });
    expect(JSON.parse(searchCalls()[0][1].body)).toEqual({ text: "Microservices Kafka" });
    expect(screen.getByRole("textbox", { name: "Resume search" })).toHaveValue("Microservices Kafka");
    const snippet = within(item).getByText("From the resume").parentElement!;
    expect(snippet.querySelector("mark")).toHaveTextContent("Microservices");
    expect(snippet).toHaveTextContent("Built Microservices on <b>Kafka</b>"); // resume text is text, never markup
  });

  it("puts the typed resume search in the URL with the skills", () => {
    query = "all=Java";
    render(<RecruiterFindCandidates writes sourceFilter />);
    fireEvent.change(screen.getByRole("textbox", { name: "Resume search" }), { target: { value: '  "AWS Certified"   architect ' } });
    fireEvent.click(screen.getByRole("button", { name: "Search candidates" }));
    expect(push).toHaveBeenLastCalledWith("/recruiter/find-candidates?q=%22AWS+Certified%22+architect&all=Java", { scroll: false });
  });

  it("shows the API's notice when the resume search has only common words", async () => {
    query = "q=the+and";
    searchReply = () => res({
      ...result, items: [], total: 0, terms: [], notice: "Your resume search only has common words like “the” or “and”, so it matches nothing. Add a more specific word.",
      facets: { experience: [{ key: "none", count: 0 }], location: [], availability: [{ key: "none", count: 0 }] },
    });
    render(<RecruiterFindCandidates writes sourceFilter />);
    expect(await screen.findByText(/only has common words/)).toBeInTheDocument();
    expect(screen.queryByText("No candidates match. Remove a skill or a filter to see more.")).toBeNull();
  });

  it("offers the first page when a hand-edited offset is past the end (QA-07)", async () => {
    query = "all=Java&offset=500";
    searchReply = () => res({ ...result, items: [], offset: 500 });
    render(<RecruiterFindCandidates writes sourceFilter />);
    fireEvent.click(await screen.findByRole("button", { name: "Go to the first page" }));
    expect(push).toHaveBeenLastCalledWith("/recruiter/find-candidates?all=Java", { scroll: false });
    expect(screen.queryByRole("navigation", { name: "Result pages" })).toBeNull();
  });
});
