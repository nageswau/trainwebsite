import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ApplicationFilterBar from "@/components/ApplicationFilterBar";
import CounselorLeadsPanel from "@/components/CounselorLeadsPanel";
import CounselorQuickSearch from "@/components/CounselorQuickSearch";
import PortalPage from "@/components/PortalPage";
import { serverApi } from "@/lib/api";

// ccrm-012 (DEC-SCOPE-246): the counselor's list filters (QS6/QS7), the quick search (QS1-QS5) and the dashboard placement (QS8).
const push = vi.fn();
const replace = vi.fn();
let search = "";
let pathname = "/overseas/counselor/applications";
vi.mock("next/navigation", () => ({
  notFound: () => { throw new Error("notFound"); },
  useRouter: () => ({ push, replace }),
  usePathname: () => pathname,
  useSearchParams: () => new URLSearchParams(search),
}));
vi.mock("@/lib/api", async () => ({ ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")), serverApi: vi.fn() }));
vi.mock("@/components/PortalShell", () => ({ default: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock("@/components/WorkflowPanel", () => ({ default: () => null }));
vi.mock("@/components/RefreshOnHistoryNav", () => ({ default: () => null }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const fetchMock = vi.fn();
beforeEach(() => {
  search = "";
  pathname = "/overseas/counselor/applications";
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  push.mockReset();
  replace.mockReset();
  vi.unstubAllGlobals();
});

const FILTERS = {
  agency: null, counselor: null, agencies: [],
  country: null, university: null, intake: null, stage: null, sub_status: null, from: null, to: null,
  countries: [{ value: "c-uk", label: "United Kingdom" }],
  universities: [{ value: "u1", label: "Uni One" }],
  intakes: [{ value: "Sep 2027", label: "Sep 2027" }],
  stages: [{ value: "offer", label: "Offer" }, { value: "visa_documentation", label: "Visa documentation" }],
  sub_statuses: [
    { value: "conditional_offer", label: "Conditional offer", stage: "offer" },
    { value: "visa_applied", label: "Visa applied", stage: "visa_documentation" },
  ],
};

describe("ApplicationFilterBar ccrm-012 filters", () => {
  it("puts each new filter in the URL beside the existing ones", () => {
    render(<ApplicationFilterBar filters={{ ...FILTERS, agency: "any" }} />);
    fireEvent.change(screen.getByLabelText("Destination"), { target: { value: "c-uk" } });
    expect(push).toHaveBeenLastCalledWith("/overseas/counselor/applications?agency=any&country=c-uk");
    fireEvent.change(screen.getByLabelText("Created from"), { target: { value: "2026-01-01" } });
    expect(push).toHaveBeenLastCalledWith("/overseas/counselor/applications?agency=any&from=2026-01-01");
  });

  it("offers only the chosen stage's sub-statuses and drops one that no longer fits", () => {
    render(<ApplicationFilterBar filters={{ ...FILTERS, stage: "offer", sub_status: "conditional_offer" }} />);
    const options = Array.from((screen.getByLabelText("Sub-status") as HTMLSelectElement).options).map((o) => o.textContent);
    expect(options).toEqual(["All", "Conditional offer"]);
    fireEvent.change(screen.getByLabelText("Stage"), { target: { value: "visa_documentation" } });
    expect(push).toHaveBeenLastCalledWith("/overseas/counselor/applications?stage=visa_documentation");
  });

  it("shows Clear filters for a new filter alone, and no new controls on an older payload", () => {
    const { rerender } = render(<ApplicationFilterBar filters={{ ...FILTERS, intake: "Sep 2027" }} />);
    expect(screen.getByRole("link", { name: "Clear filters" })).toHaveAttribute("href", "/overseas/counselor/applications");
    rerender(<ApplicationFilterBar filters={{ agency: null, counselor: null, agencies: [] }} />);
    expect(screen.queryByLabelText("Destination")).toBeNull();
    expect(screen.queryByLabelText("Created from")).toBeNull();
  });
});

describe("CounselorLeadsPanel ccrm-012 filters", () => {
  const page = { items: [], total: 0, limit: 20, offset: 0 };

  it("sends the URL's filters to the API and says when nothing matches", async () => {
    search = "priority=hot&stage=follow_up&foo=1";
    pathname = "/overseas/counselor/leads";
    fetchMock.mockResolvedValue(res(page));
    render(<CounselorLeadsPanel division="overseas" />);
    expect(await screen.findByText("No leads match these filters.")).toBeInTheDocument();
    const url = new URL(fetchMock.mock.calls[0][0] as string, "http://x");
    expect([url.searchParams.get("stage"), url.searchParams.get("priority"), url.searchParams.get("foo")]).toEqual(["follow_up", "hot", null]);
    expect((screen.getByLabelText("Priority") as HTMLSelectElement).value).toBe("hot");
  });

  it("writes a changed filter to the URL", async () => {
    pathname = "/overseas/counselor/leads";
    fetchMock.mockResolvedValue(res(page));
    render(<CounselorLeadsPanel division="overseas" />);
    await screen.findByText("No leads have been handed to you yet.");
    fireEvent.change(screen.getByLabelText("Priority"), { target: { value: "cold" } });
    expect(replace).toHaveBeenCalledWith("/overseas/counselor/leads?priority=cold");
  });

  it("shows the API's reason for a refused filter", async () => {
    search = "from=2026-03-01&to=2026-02-01";
    fetchMock.mockResolvedValue(res({ detail: "The start date must be on or before the end date" }, 422));
    render(<CounselorLeadsPanel division="overseas" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("The start date must be on or before the end date");
  });
});

const RESULT = {
  q: "zara",
  leads: { items: [], more: false },
  students: { items: [{ id: "s1", code: "Z1234", label: "Zara Quill", detail: "zara@example.local", href: "/overseas/counselor/students/s1/notes" }], more: true },
  applications: { items: [{ id: "a1", code: "APP-000001", label: "Zara Quill", detail: "Uni One · Sep 2027", href: "/overseas/counselor/applications" }], more: false },
};

describe("CounselorQuickSearch", () => {
  it("refuses fewer than 3 characters without calling the API", () => {
    render(<CounselorQuickSearch />);
    fireEvent.change(screen.getByLabelText("Name, phone, email or ID"), { target: { value: " ab " } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Type at least 3 characters");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("lists each group with links, a 'more' hint and an empty group", async () => {
    fetchMock.mockResolvedValue(res(RESULT));
    render(<CounselorQuickSearch />);
    fireEvent.change(screen.getByLabelText("Name, phone, email or ID"), { target: { value: "zara" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByRole("heading", { name: "Students (1+)" })).toBeInTheDocument();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/counselor/search?q=zara");
    expect(screen.getAllByRole("link", { name: "Zara Quill" })[0]).toHaveAttribute("href", "/overseas/counselor/students/s1/notes");
    expect(screen.getByText("APP-000001 · Uni One · Sep 2027")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Leads (0)" })).toBeInTheDocument();
    expect(screen.getByText("Showing the first 10 -- refine your search.")).toBeInTheDocument();
  });

  it("says when nothing matches, and shows a throttle refusal", async () => {
    fetchMock.mockResolvedValueOnce(res({ ...RESULT, students: { items: [], more: false }, applications: { items: [], more: false } }));
    render(<CounselorQuickSearch />);
    fireEvent.change(screen.getByLabelText("Name, phone, email or ID"), { target: { value: "zara" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByText(/Nothing in your leads, students or applications matches/)).toBeInTheDocument();
    fetchMock.mockResolvedValueOnce(res({ detail: "Too many searches; try again in 12 seconds" }, 429));
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Too many searches; try again in 12 seconds"));
  });
});

describe("PortalPage ccrm-012", () => {
  const api = vi.mocked(serverApi);
  const payload = { title: "Counselor Dashboard", subtitle: "", metrics: [], actions: [], panels: [], columns: [{ key: "student", label: "Student" }], rows: [] };
  beforeEach(() => {
    api.mockReset();
    api.mockImplementation((path: string) => Promise.resolve(path === "/api/v1/auth/me" ? { id: "u1", role: "counselor", full_name: "C", email: "c@x" } : { ...payload, filters: path.includes("applications") ? FILTERS : undefined }));
  });

  it("puts the quick search on the overseas counselor's dashboard", async () => {
    render(await PortalPage({ division: "overseas", role: "counselor", section: "dashboard" }));
    expect(screen.getByRole("search")).toBeInTheDocument();
  });

  it("forwards the new filter keys to the API", async () => {
    render(await PortalPage({ division: "overseas", role: "counselor", section: "applications", query: { stage: "offer", from: "2026-01-01", foo: "1" } }));
    expect(api.mock.calls.map((c) => c[0]).filter((p) => String(p).startsWith("/api/v1/portal/"))).toEqual(["/api/v1/portal/overseas/counselor/applications?stage=offer&from=2026-01-01"]);
  });
});
