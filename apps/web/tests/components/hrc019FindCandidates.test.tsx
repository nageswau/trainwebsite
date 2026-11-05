import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterFindCandidates from "@/components/RecruiterFindCandidates";
import { clearPermissions } from "@/lib/usePermissions";

// hrc-019 (DEC-SCOPE-399): grouped collapsible filters, one removable chip per active filter (AC2), the sort select (AC3), the package
// group only with the grant (S9) and the card's "why matched" line (S11).
let query = "";
const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }), usePathname: () => "/recruiter/find-candidates", useSearchParams: () => new URLSearchParams(query),
}));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const CAT = "0f8fad5b-d9cb-469f-a165-70867728950e";
const card = {
  id: "c1", candidate_code: "CAN-000001", name: "Rahul Kumar", preferred_role: "Java Developer", current_company: null, experience_months: 36,
  location: "Hyderabad", notice_days: 0, source: { id: "s2", name: "Referral", active: true }, source_detail: null, status: "available",
  skills: [{ name: "Java", level: "advanced", status: "verified", matched: true }],
  match: { required: [{ term: "java", skill: "Java", held: true }], preferred: [{ term: "Docker", skill: "Docker", held: false }] },
};
const result = {
  items: [card], total: 1, limit: 50, offset: 0,
  facets: { experience: [], location: [], availability: [] }, terms: [{ term: "java", skill: { id: "k1", name: "Java" }, also: [] }],
};
let fetchMock: ReturnType<typeof vi.fn>;
let granted: string[] | null;

beforeEach(() => {
  query = "";
  granted = null;
  clearPermissions();
  push.mockReset();
  fetchMock = vi.fn((url: string) => {
    if (url.startsWith("/api/v1/recruiter/catalogue/candidate-sources")) return Promise.resolve(res({ items: [], total: 0, limit: 100, offset: 0 }));
    if (url.startsWith("/api/v1/recruiter/skill-categories")) return Promise.resolve(res({ items: [{ id: CAT, name: "Pharmacy", active: true }], total: 1 }));
    if (url === "/api/v1/auth/me/permissions") return Promise.resolve(granted ? res({ permissions: granted }) : res({}, 500));
    return Promise.resolve(res(result));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const pushed = () => new URLSearchParams(String(push.mock.calls.at(-1)?.[0]).split("?")[1] ?? "");
const searchBodies = () =>
  fetchMock.mock.calls.filter(([u]) => String(u).startsWith("/api/v1/recruiter/candidates/search")).map(([, init]) => JSON.parse(String(init?.body)));

describe("hrc-019 Find Candidates", () => {
  it("groups the filters in collapsible sections; new groups start closed unless they hold a filter", async () => {
    query = "all=java&degree=B.Tech";
    render(<RecruiterFindCandidates writes sourceFilter />);
    await screen.findByRole("listitem", { name: /Rahul Kumar/ });
    const section = (name: RegExp) => screen.getByText(name, { selector: "summary" }).closest("details")!;
    expect(section(/^Education/)).toHaveAttribute("open");
    expect(section(/^Education/).querySelector("summary")).toHaveTextContent("Education (1)");
    expect(section(/^Documents and applications/)).not.toHaveAttribute("open");
    expect(section(/^Experience/)).toHaveAttribute("open"); // today's fields stay in view
    expect(screen.getByLabelText("Degree")).toHaveValue("B.Tech");
  });

  it("sends the new filters and pushes them to the URL on Search", async () => {
    query = "all=java";
    render(<RecruiterFindCandidates writes sourceFilter />);
    await screen.findByRole("listitem", { name: /Rahul Kumar/ });
    expect(screen.queryByLabelText("Institution")).toBeNull(); // a closed group renders no controls
    const education = screen.getByText("Education", { selector: "summary" }).closest("details")!;
    education.open = true;
    fireEvent(education, new Event("toggle"));
    fireEvent.change(await screen.findByLabelText("Institution"), { target: { value: "JNTU" } });
    fireEvent.click(within(screen.getByRole("group", { name: "Employment type" })).getByRole("checkbox", { name: "Contract" }));
    fireEvent.change(screen.getByLabelText("Primary recruiter"), { target: { value: "me" } });
    fireEvent.click(screen.getByRole("button", { name: "Search candidates" }));
    const next = pushed();
    expect(next.get("inst")).toBe("JNTU");
    expect(next.get("owner")).toBe("me");
    expect(next.getAll("emp_type")).toEqual(["contract"]);
  });

  it("shows one chip per active filter and removes just that one (AC2)", async () => {
    query = "all=java&degree=B.Tech&city=Pune&work_mode=remote";
    render(<RecruiterFindCandidates writes sourceFilter />);
    await screen.findByRole("listitem", { name: /Rahul Kumar/ });
    const chips = screen.getByRole("list", { name: "Active filters" });
    expect(within(chips).getAllByRole("listitem").map((li) => li.textContent?.replace("×", "").trim())).toEqual(["Degree: B.Tech", "City: Pune", "Work mode: Remote"]);
    fireEvent.click(within(chips).getByRole("button", { name: "Remove City: Pune" }));
    const next = pushed();
    expect(next.get("city")).toBeNull();
    expect(next.get("degree")).toBe("B.Tech");
    expect(next.get("work_mode")).toBe("remote");
    expect(next.getAll("all")).toEqual(["java"]);
  });

  it("names a category chip and sends the category (a category alone is a search)", async () => {
    query = `cat=${CAT}`;
    render(<RecruiterFindCandidates writes sourceFilter />);
    expect(await screen.findByRole("button", { name: "Remove Skill category: Pharmacy" })).toBeInTheDocument();
    expect(searchBodies().at(-1)).toEqual({ category_ids: [CAT] });
  });

  it("sorts at once from the results header (AC3) and offers the package sort only with the grant", async () => {
    query = "all=java&offset=50";
    render(<RecruiterFindCandidates writes sourceFilter />);
    const sort = await screen.findByLabelText("Sort by");
    expect(within(sort).queryByRole("option", { name: "Lowest expected salary" })).toBeNull();
    fireEvent.change(sort, { target: { value: "experience" } });
    expect(pushed().get("sort")).toBe("experience");
    expect(pushed().get("offset")).toBeNull();
    cleanup();
    granted = ["candidates.compensation.view"];
    render(<RecruiterFindCandidates writes sourceFilter />);
    expect(await screen.findByRole("option", { name: "Lowest expected salary" })).toBeInTheDocument();
    expect(screen.getByLabelText("Include unknown salary")).toBeInTheDocument();
  });

  it("QA-01: a read-only role (hr_team cannot read the Skills Master) gets no category filter and no category request", async () => {
    query = "all=java";
    render(<RecruiterFindCandidates writes={false} sourceFilter={false} />);
    await screen.findByRole("listitem", { name: /Rahul Kumar/ });
    const skills = screen.getByText("More skill filters", { selector: "summary" }).closest("details")!;
    skills.open = true;
    fireEvent(skills, new Event("toggle"));
    expect(await screen.findByLabelText("Minimum skill level")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Skill category" })).toBeNull();
    expect(fetchMock.mock.calls.some(([u]) => String(u).startsWith("/api/v1/recruiter/skill-categories"))).toBe(false);
  });

  it("hides the package group without the grant", async () => {
    query = "all=java";
    render(<RecruiterFindCandidates writes sourceFilter />);
    await screen.findByRole("listitem", { name: /Rahul Kumar/ });
    expect(screen.queryByText(/^Package/, { selector: "summary" })).toBeNull();
    expect(screen.queryByLabelText("Include unknown salary")).toBeNull();
  });

  it("explains each card: matched skills and missing nice-to-haves (S11)", async () => {
    query = "all=java&pref=Docker";
    render(<RecruiterFindCandidates writes sourceFilter />);
    const item = await screen.findByRole("listitem", { name: /Rahul Kumar/ });
    expect(within(item).getByText("Why matched")).toBeInTheDocument();
    expect(within(item).getByText(/Matches: Java/)).toBeInTheDocument();
    expect(within(item).getByText(/Missing nice-to-have: Docker/)).toBeInTheDocument();
    expect(searchBodies().at(-1)).toEqual({ all: ["java"], preferred: ["Docker"] });
  });

  it("adds nice-to-have skills as chips", async () => {
    render(<RecruiterFindCandidates writes sourceFilter />);
    const box = screen.getByRole("textbox", { name: "Nice to have (ranks, never excludes)" });
    fireEvent.change(box, { target: { value: "Docker" } });
    fireEvent.keyDown(box, { key: "Enter" });
    fireEvent.click(screen.getByRole("button", { name: "Search candidates" }));
    expect(pushed().getAll("pref")).toEqual(["Docker"]);
  });
});
