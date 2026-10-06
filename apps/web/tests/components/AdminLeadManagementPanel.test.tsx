import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AdminLeadManagementPanel from "@/components/AdminLeadManagementPanel";

// tel-003: filters, search and page live in the URL; the test drives them through a mutable search string.
let search = "";
const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), push }),
  usePathname: () => "/it/admin/leads",
  useSearchParams: () => new URLSearchParams(search),
}));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const pageOf = (items: unknown[], total = items.length, offset = 0) => ({ items, total, limit: 50, offset });
type Row = Record<string, unknown>;
const row = (id: string, over: Row = {}): Row => ({
  id, lead_code: `LD-00000${id.length}`, name: `Lead ${id}`, email: `${id}@example.com`, phone: null, division: "it", subject: "Python",
  status: "new", source: "website", crm_sync_status: "sent", priority: "warm", whatsapp_number: null, city: null, state: null,
  qualification: null, passing_year: null, institution: null, created_at: "2026-10-06T05:00:00Z", stage_changed_at: "2026-10-06T05:00:00Z",
  product: null, campaign: null, telecaller: null, counselor: null, organization: null, bdm: null, converted_user: null, ...over,
});
const stMary = { id: "o1", code: "ORG-000001", name: "St Mary" };
const rows = [
  row("w1", { lead_code: "LD-000123", source: "instagram", product: { id: "p1", name: "Cyber Security" }, campaign: { id: "c1", name: "Sep 2026" },
    telecaller: { id: "t1", full_name: "Tara Caller" }, priority: "hot" }),
  row("b1", { source: "bdm", organization: stMary, bdm: { id: "u1", full_name: "Asha" } }),
];
const products = pageOf([{ id: "p1", group: "it", name: "Cyber Security", team: "it", program: null, active: true, sort_order: 1 }]);
const campaigns = pageOf([{ id: "c1", name: "Sep 2026", source: "instagram", product: { id: "p1", name: "Cyber Security", group: "it", active: true },
  start_date: "2026-09-01", end_date: null, active: true }]);
const telecallers = [{ id: "t1", name: "Tara Caller", role: "telecaller" }];

let leadsPage: () => Promise<Response>;
let fetchMock: ReturnType<typeof vi.fn>;
const leadCalls = () => fetchMock.mock.calls.map(([u]) => String(u)).filter((u) => u.startsWith("/api/v1/admin/leads?"));
beforeEach(() => {
  search = "";
  push.mockReset();
  leadsPage = () => Promise.resolve(res(pageOf(rows)));
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method) return Promise.resolve(res({}, 500));
    if (url.startsWith("/api/v1/admin/leads?")) return leadsPage();
    if (url.startsWith("/api/v1/telecaller/products")) return Promise.resolve(res(products));
    if (url.startsWith("/api/v1/telecaller/campaigns")) return Promise.resolve(res(campaigns));
    if (url.startsWith("/api/v1/admin/users?role=telecaller")) return Promise.resolve(res(telecallers));
    return Promise.resolve(res({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
const tableRow = async (name: string) => (await screen.findByRole("rowheader", { name })).closest("tr") as HTMLElement;
const pushedQuery = () => new URLSearchParams(String(push.mock.calls.at(-1)?.[0]).split("?")[1] ?? "");

describe("AdminLeadManagementPanel (ADM-002, bdm-017 spec §6, tel-003 spec §5)", () => {
  it("asks the API for one page with the filters, search and offset from the URL", async () => {
    search = "status=contacted&product_id=p1&q=asha&offset=50";
    render(<AdminLeadManagementPanel />);
    await tableRow("Lead w1");
    const query = new URLSearchParams(leadCalls()[0].split("?")[1]);
    expect(Object.fromEntries(query)).toEqual({ status: "contacted", product_id: "p1", q: "asha", limit: "50", offset: "50" });
  });

  it("shows the Lead ID, interest, source and campaign, telecaller and priority of each lead", async () => {
    render(<AdminLeadManagementPanel />);
    const tr = await tableRow("Lead w1");
    for (const text of ["LD-000123", "Cyber Security", "Instagram · Sep 2026", "Tara Caller", "Hot"]) expect(within(tr).getByText(text)).toBeInTheDocument();
    const b1 = await tableRow("Lead b1");
    expect(within(b1).getByText("ORG-000001 · St Mary")).toBeInTheDocument();
    expect(within(b1).getByText("Python")).toBeInTheDocument(); // no product: the subject is the interest
    for (const name of ["Lead ID", "Interest", "Source · Campaign", "Telecaller", "Priority", "Organization"]) {
      expect(screen.getByRole("columnheader", { name })).toBeInTheDocument();
    }
  });

  it("spans the full width and keeps the lead's name in view while the columns scroll (QA17-03)", async () => {
    render(<AdminLeadManagementPanel />);
    const tr = await tableRow("Lead b1");
    expect(screen.getByRole("heading", { name: "Manage leads" }).closest(".action-card")).toHaveClass("lead-management");
    expect(tr.closest("table")!.parentElement).toHaveClass("table-scroll");
    expect(tr.firstElementChild).toHaveAttribute("scope", "row");
  });

  it("offers the catalogue, the division's telecallers and the page's organizations as filters", async () => {
    render(<AdminLeadManagementPanel />);
    await tableRow("Lead w1");
    await waitFor(() => expect(within(screen.getByLabelText("Telecaller")).getByRole("option", { name: "Tara Caller" })).toBeInTheDocument());
    expect(within(screen.getByLabelText("Product")).getByRole("option", { name: "Cyber Security" })).toBeInTheDocument();
    expect(within(screen.getByLabelText("Campaign")).getByRole("option", { name: "Sep 2026" })).toBeInTheDocument();
    expect(within(screen.getByLabelText("Source")).getByRole("option", { name: "Exhibition/Event" })).toBeInTheDocument();
    expect(within(screen.getByLabelText("Organization")).getByRole("option", { name: "ORG-000001 · St Mary" })).toBeInTheDocument();
  });

  it("a filter change goes into the URL and starts again from the first page", async () => {
    search = "offset=50&q=asha";
    render(<AdminLeadManagementPanel />);
    await tableRow("Lead w1");
    fireEvent.change(screen.getByLabelText("Stage"), { target: { value: "contacted" } });
    expect(Object.fromEntries(pushedQuery())).toEqual({ q: "asha", status: "contacted" });
    fireEvent.change(screen.getByLabelText("Organization"), { target: { value: "o1" } });
    expect(pushedQuery().get("bdm_organization_id")).toBe("o1");
  });

  it("searches on submit and clears the search", async () => {
    render(<AdminLeadManagementPanel />);
    await tableRow("Lead w1");
    fireEvent.change(screen.getByLabelText("Search leads"), { target: { value: " LD-000123 " } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(Object.fromEntries(pushedQuery())).toEqual({ q: "LD-000123" });
  });

  it("pages through the list when there are more than 50 leads", async () => {
    leadsPage = () => Promise.resolve(res(pageOf(rows, 120)));
    render(<AdminLeadManagementPanel />);
    await tableRow("Lead w1");
    expect(screen.getByText("Showing 1–2 of 120")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous page" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(pushedQuery().get("offset")).toBe("50");
  });

  it("has no pager when one page holds every lead", async () => {
    render(<AdminLeadManagementPanel />);
    await tableRow("Lead w1");
    expect(screen.queryByRole("navigation", { name: "Lead pages" })).toBeNull();
  });

  it("a failed load says so and retries", async () => {
    leadsPage = () => Promise.resolve(res({ detail: "boom" }, 500));
    render(<AdminLeadManagementPanel />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load leads.");
    leadsPage = () => Promise.resolve(res(pageOf(rows)));
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await tableRow("Lead w1");
  });

  it("tells an empty list apart from a filter that matches nothing", async () => {
    leadsPage = () => Promise.resolve(res(pageOf([])));
    render(<AdminLeadManagementPanel />);
    expect(await screen.findByText("No leads found.")).toBeInTheDocument();
    cleanup();
    search = "source=google";
    render(<AdminLeadManagementPanel />);
    expect(await screen.findByText("No leads match these filters.")).toBeInTheDocument();
  });

  it("links a student by email and shows who the lead converted to", async () => {
    render(<AdminLeadManagementPanel />);
    const tr = await tableRow("Lead b1");
    fetchMock.mockImplementationOnce(() => Promise.resolve(res({ ...rows[1], status: "converted", converted_user: { id: "s1", full_name: "Stu Dent", email: "stu@example.com" } })));
    fireEvent.click(within(tr).getByRole("button", { name: "Link student to Lead b1" }));
    fireEvent.change(within(tr).getByLabelText("Student account email for Lead b1"), { target: { value: "stu@example.com" } });
    fireEvent.click(within(tr).getByRole("button", { name: "Link" }));
    await waitFor(() => expect(within(tr).getByText("Stu Dent (stu@example.com)")).toBeInTheDocument());
    expect(within(tr).getByRole("status")).toHaveTextContent("Student linked.");
    const [url, init] = fetchMock.mock.calls.at(-1) as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/admin/leads/b1/conversion");
    expect([init.method, JSON.parse(String(init.body))]).toEqual(["POST", { student_email: "stu@example.com" }]);
  });

  it("a refused link keeps the email and shows the server's words in the row", async () => {
    render(<AdminLeadManagementPanel />);
    const tr = await tableRow("Lead b1");
    fetchMock.mockImplementationOnce(() => Promise.resolve(res({ detail: "Enter the email of an active student account in this lead's division" }, 422)));
    fireEvent.click(within(tr).getByRole("button", { name: "Link student to Lead b1" }));
    fireEvent.change(within(tr).getByLabelText("Student account email for Lead b1"), { target: { value: "x@example.com" } });
    fireEvent.click(within(tr).getByRole("button", { name: "Link" }));
    await waitFor(() => expect(within(tr).getByRole("status")).toHaveTextContent("Enter the email of an active student account"));
    expect(within(tr).getByLabelText("Student account email for Lead b1")).toHaveValue("x@example.com");
  });

  it("unlinks after a confirm", async () => {
    leadsPage = () => Promise.resolve(res(pageOf([row("c1", { converted_user: { id: "s1", full_name: "Stu Dent", email: "stu@example.com" }, status: "converted" })])));
    render(<AdminLeadManagementPanel />);
    const tr = await tableRow("Lead c1");
    fetchMock.mockImplementationOnce(() => Promise.resolve(res(row("c1", { status: "converted" }))));
    fireEvent.click(within(tr).getByRole("button", { name: "Unlink student from Lead c1" }));
    fireEvent.click(within(tr).getByRole("button", { name: "Yes, unlink" }));
    await waitFor(() => expect(within(tr).getByRole("button", { name: "Link student to Lead c1" })).toBeInTheDocument());
    expect((fetchMock.mock.calls.at(-1) as unknown as [string, RequestInit])[1].method).toBe("DELETE");
  });

  it("updates a lead's status in place", async () => {
    render(<AdminLeadManagementPanel />);
    const tr = await tableRow("Lead w1");
    fetchMock.mockImplementationOnce(() => Promise.resolve(res({ ok: true })));
    fireEvent.change(within(tr).getByLabelText("Lead w1 status"), { target: { value: "contacted" } });
    await waitFor(() => expect(within(tr).getByRole("status")).toHaveTextContent("Lead updated."));
    expect(within(tr).getByLabelText("Lead w1 status")).toHaveValue("contacted");
  });
});
