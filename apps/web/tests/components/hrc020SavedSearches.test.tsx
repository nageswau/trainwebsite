import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterFindCandidates from "@/components/RecruiterFindCandidates";
import { clearPermissions } from "@/lib/usePermissions";

// hrc-020 (DEC-SCOPE-401): load / save / update / delete saved searches (AC1, the removed-filter notice) and the export button, shown
// only with `candidates.export` (AC2 is the API's; the page hides what the role cannot do).
let query = "";
const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }), usePathname: () => "/recruiter/find-candidates", useSearchParams: () => new URLSearchParams(query),
}));

const res = (body: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(body), { status });
const card = {
  id: "c1", candidate_code: "CAN-000001", name: "Rahul Kumar", preferred_role: "Java Developer", current_company: null, experience_months: 36,
  location: "Hyderabad", notice_days: 0, source: { id: "s2", name: "Referral", active: true }, source_detail: null, status: "available",
  skills: [{ name: "Java", level: "advanced", status: "verified", matched: true }],
};
const result = { items: [card], total: 1, limit: 50, offset: 0, facets: { experience: [], location: [], availability: [] }, terms: [] };
const mine = { id: "s1", name: "Pune Java", filters: { all: ["Java"], city: "Pune", sort: "experience" }, ignored: [], shared: false, mine: true,
  can_edit: true, owner: { id: "u1", name: "Me" } };
const theirs = { id: "s2", name: "Team Python", filters: { all: ["Python"] }, ignored: ["retired_filter"], shared: true, mine: false,
  can_edit: false, owner: { id: "u2", name: "Asha" } };
let saved: unknown[];
let granted: string[];
let fetchMock: ReturnType<typeof vi.fn>;
const SAVED = "/api/v1/recruiter/candidates/saved-searches";

beforeEach(() => {
  query = "";
  saved = [mine, theirs];
  granted = [];
  clearPermissions();
  push.mockReset();
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    if (url === "/api/v1/auth/me/permissions") return Promise.resolve(res({ permissions: granted }));
    if (url.startsWith("/api/v1/recruiter/catalogue") || url.startsWith("/api/v1/recruiter/skill-categories")) return Promise.resolve(res({ items: [], total: 0 }));
    if (url === SAVED && method === "GET") return Promise.resolve(res({ items: saved }));
    if (url === SAVED && method === "POST") {
      const body = JSON.parse(String(init?.body));
      return Promise.resolve(res({ ...mine, id: "s9", name: body.name, filters: body.filters, shared: body.shared }, 201));
    }
    if (url.startsWith(`${SAVED}/`) && method === "PATCH") return Promise.resolve(res({ ...mine, filters: JSON.parse(String(init?.body)).filters }));
    if (url.startsWith(`${SAVED}/`) && method === "DELETE") return Promise.resolve(res(null, 204));
    if (url.includes("/search/export")) return Promise.resolve(new Response("csv", { status: 200, headers: { "Content-Type": "text/csv" } }));
    return Promise.resolve(res(result));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const calls = (method: string, prefix: string) =>
  fetchMock.mock.calls.filter(([u, init]) => String(u).startsWith(prefix) && (init?.method ?? "GET") === method);
const pushed = () => new URLSearchParams(String(push.mock.calls.at(-1)?.[0]).split("?")[1] ?? "");

describe("hrc-020 saved searches", () => {
  it("lists my searches and shared ones; choosing one restores its filters in the URL", async () => {
    render(<RecruiterFindCandidates writes sourceFilter />);
    const picker = await screen.findByLabelText("Load a saved search");
    expect(await screen.findByRole("option", { name: "Pune Java" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Team Python — Asha" })).toBeInTheDocument();
    fireEvent.change(picker, { target: { value: "s1" } });
    const params = pushed();
    expect(params.getAll("all")).toEqual(["Java"]);
    expect(params.get("city")).toBe("Pune");
    expect(params.get("sort")).toBe("experience");
  });

  it("names the filters a saved search used that are no longer available", async () => {
    render(<RecruiterFindCandidates writes sourceFilter />);
    fireEvent.change(await screen.findByLabelText("Load a saved search"), { target: { value: "s2" } });
    expect(screen.getByText(/no longer available and were ignored: retired_filter/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete" })).toBeNull(); // not mine
  });

  it("saves the current search with a name and the shared flag", async () => {
    query = "all=Java&exp_min=2";
    render(<RecruiterFindCandidates writes sourceFilter />);
    await screen.findByRole("listitem", { name: /Rahul Kumar/ });
    fireEvent.click(await screen.findByRole("button", { name: "Save this search" }));
    fireEvent.change(screen.getByLabelText("Saved search name"), { target: { value: "Java 2+" } });
    fireEvent.click(screen.getByLabelText("Share with the team"));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText("Saved “Java 2+”.");
    const [, init] = calls("POST", SAVED)[0];
    expect(JSON.parse(String(init?.body))).toEqual({ name: "Java 2+", shared: true, filters: { all: ["Java"], experience_min_months: 24 } });
    expect(screen.getByLabelText("Load a saved search")).toHaveValue("s9");
  });

  it("cannot save before searching", async () => {
    render(<RecruiterFindCandidates writes sourceFilter />);
    await screen.findByLabelText("Load a saved search");
    expect(screen.queryByRole("button", { name: "Save this search" })).toBeNull();
  });

  it("shows the API's message when a save is refused", async () => {
    query = "all=Java";
    render(<RecruiterFindCandidates writes sourceFilter />);
    await screen.findByRole("listitem", { name: /Rahul Kumar/ });
    const original = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation((url: string, init?: RequestInit) =>
      url === SAVED && init?.method === "POST" ? Promise.resolve(res({ detail: "You already have a saved search with this name" }, 409)) : original(url, init));
    fireEvent.click(await screen.findByRole("button", { name: "Save this search" }));
    fireEvent.change(screen.getByLabelText("Saved search name"), { target: { value: "Pune Java" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("You already have a saved search with this name");
  });

  it("updates and deletes my own saved search", async () => {
    query = "all=Go";
    render(<RecruiterFindCandidates writes sourceFilter />);
    await screen.findByRole("listitem", { name: /Rahul Kumar/ });
    fireEvent.change(await screen.findByLabelText("Load a saved search"), { target: { value: "s1" } });
    fireEvent.click(screen.getByRole("button", { name: "Update with current filters" }));
    await waitFor(() => expect(calls("PATCH", `${SAVED}/s1`)).toHaveLength(1));
    expect(JSON.parse(String(calls("PATCH", `${SAVED}/s1`)[0][1]?.body))).toEqual({ filters: { all: ["Go"] } });
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete" }));
    await screen.findByText("Deleted “Pune Java”.");
    expect(calls("DELETE", `${SAVED}/s1`)).toHaveLength(1);
    expect(screen.queryByRole("option", { name: "Pune Java" })).toBeNull();
  });

  it("says so when the list cannot load, and retries", async () => {
    const original = fetchMock.getMockImplementation()!;
    let fail = true;
    fetchMock.mockImplementation((url: string, init?: RequestInit) =>
      url === SAVED && (init?.method ?? "GET") === "GET" && fail ? Promise.resolve(res({}, 500)) : original(url, init));
    render(<RecruiterFindCandidates writes sourceFilter />);
    await screen.findByText("Unable to load saved searches.");
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "Retry loading saved searches" }));
    expect(await screen.findByRole("option", { name: "Pune Java" })).toBeInTheDocument();
  });
});

describe("hrc-020 export", () => {
  it("is hidden without candidates.export", async () => {
    query = "all=Java";
    render(<RecruiterFindCandidates writes sourceFilter />);
    await screen.findByRole("listitem", { name: /Rahul Kumar/ });
    expect(screen.queryByRole("button", { name: /Export/ })).toBeNull();
  });

  it("downloads the current search as CSV or Excel with the grant", async () => {
    granted = ["candidates.export"];
    query = "all=Java&sort=experience";
    const createObjectURL = vi.fn(() => "blob:x");
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL, revokeObjectURL: vi.fn() }));
    render(<RecruiterFindCandidates writes sourceFilter />);
    fireEvent.click(await screen.findByRole("button", { name: "Export CSV" }));
    await waitFor(() => expect(createObjectURL).toHaveBeenCalled());
    const [url, init] = calls("POST", "/api/v1/recruiter/candidates/search/export")[0];
    expect(url).toBe("/api/v1/recruiter/candidates/search/export?format=csv");
    expect(JSON.parse(String(init?.body))).toEqual({ all: ["Java"], sort: "experience" });
    fireEvent.click(screen.getByRole("button", { name: "Export Excel" }));
    await waitFor(() => expect(calls("POST", "/api/v1/recruiter/candidates/search/export")).toHaveLength(2));
    expect(calls("POST", "/api/v1/recruiter/candidates/search/export")[1][0]).toContain("format=xlsx");
  });

  it("shows the API's refusal (cap, throttle)", async () => {
    granted = ["candidates.export"];
    query = "all=Java";
    const original = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation((url: string, init?: RequestInit) =>
      url.includes("/search/export") ? Promise.resolve(res({ detail: "This list has more than 5,000 rows; narrow the filters" }, 422)) : original(url, init));
    render(<RecruiterFindCandidates writes sourceFilter />);
    fireEvent.click(await screen.findByRole("button", { name: "Export CSV" }));
    expect(await screen.findByText("This list has more than 5,000 rows; narrow the filters")).toBeInTheDocument();
  });
});
