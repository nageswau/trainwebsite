import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import TelecallerLeadTable from "@/components/TelecallerLeadTable";

// tel-008 (spec §3, D3): My Leads -- filters, search and page live in the URL, like the admin lead panel (tel-003).
let search = "";
const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), push }),
  usePathname: () => "/telecaller/leads",
  useSearchParams: () => new URLSearchParams(search),
}));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const pageOf = (items: unknown[], total = items.length, offset = 0) => ({ items, total, limit: 50, offset });
const lead = (id: string, over: Record<string, unknown> = {}) => ({
  id, lead_code: `LD-0000${id}`, name: `Lead ${id}`, email: `${id}@example.com`, phone: "98765 43210", whatsapp_number: null, city: null,
  state: null, qualification: null, passing_year: null, institution: null, division: "it", subject: "Python", status: "new", status_label: "New Lead",
  source: "website", priority: "warm", created_at: "2026-10-06T05:00:00Z", stage_changed_at: "2026-10-06T05:00:00Z", product: null,
  campaign: null, telecaller: { id: "t1", full_name: "Tara Caller" }, counselor: null, read_only: false, ...over,
});
const products = pageOf([{ id: "p1", group: "it", name: "Cyber Security", team: "it", program: null, active: true, sort_order: 1 }]);
const campaigns = pageOf([{ id: "c1", name: "Sep 2026", source: "instagram", product: { id: "p1", name: "Cyber Security", group: "it", active: true },
  start_date: "2026-09-01", end_date: null, active: true }]);

let leadsPage: () => Promise<Response>;
let fetchMock: ReturnType<typeof vi.fn>;
const leadCalls = () => fetchMock.mock.calls.map(([u]) => String(u)).filter((u) => u.startsWith("/api/v1/telecaller/leads?"));
beforeEach(() => {
  search = "";
  push.mockReset();
  leadsPage = () => Promise.resolve(res(pageOf([lead("1", { priority: "hot", product: { id: "p1", name: "Cyber Security" } }), lead("2")])));
  fetchMock = vi.fn((url: string) => {
    if (url.startsWith("/api/v1/telecaller/leads?")) return leadsPage();
    if (url.startsWith("/api/v1/telecaller/products")) return Promise.resolve(res(products));
    if (url.startsWith("/api/v1/telecaller/campaigns")) return Promise.resolve(res(campaigns));
    return Promise.resolve(res({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
const pushedQuery = () => new URLSearchParams(String(push.mock.calls.at(-1)?.[0]).split("?")[1] ?? "");

describe("TelecallerLeadTable (tel-008)", () => {
  it("asks the API for one page with the filters, search and offset from the URL", async () => {
    const p = "0b0d6f3e-6a0b-4c1e-9d55-2f6a1a7f0001";
    const c = "0b0d6f3e-6a0b-4c1e-9d55-2f6a1a7f0002";
    search = `status=contacted&priority=hot&product_id=${p}&campaign_id=${c}&q=asha&offset=50&junk=1`;
    render(<TelecallerLeadTable basePath="/telecaller/leads" />);
    await screen.findByRole("link", { name: "Lead 1" });
    expect(Object.fromEntries(new URLSearchParams(leadCalls()[0].split("?")[1]))).toEqual({
      status: "contacted", priority: "hot", product_id: p, campaign_id: c, q: "asha", limit: "50", offset: "50",
    });
  });

  it("links each lead to its detail page and shows Lead ID, interest, stage and priority", async () => {
    render(<TelecallerLeadTable basePath="/telecaller/leads" />);
    const link = await screen.findByRole("link", { name: "Lead 1" });
    expect(link.getAttribute("href")).toBe("/telecaller/leads/1");
    const row = link.closest("tr") as HTMLElement;
    for (const text of ["LD-00001", "Cyber Security", "New Lead", "Hot"]) expect(row.textContent).toContain(text);
    expect(screen.queryByRole("columnheader", { name: "Telecaller" })).toBeNull();
  });

  it("shows the telecaller column for a manager", async () => {
    render(<TelecallerLeadTable basePath="/telecaller/manager/leads" showTelecaller />);
    expect((await screen.findByRole("link", { name: "Lead 1" })).getAttribute("href")).toBe("/telecaller/manager/leads/1");
    expect(screen.getByRole("columnheader", { name: "Telecaller" })).toBeTruthy();
    expect(screen.getAllByText("Tara Caller")).toHaveLength(2);
  });

  it("puts a filter in the URL and starts again from the first page", async () => {
    search = "offset=50";
    render(<TelecallerLeadTable basePath="/telecaller/leads" />);
    await screen.findByRole("link", { name: "Lead 1" });
    fireEvent.change(screen.getByLabelText("Priority"), { target: { value: "hot" } });
    expect(Object.fromEntries(pushedQuery())).toEqual({ priority: "hot" });
    fireEvent.change(screen.getByLabelText("Search leads"), { target: { value: "  9876 " } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(pushedQuery().get("q")).toBe("9876");
  });

  it("says when there are no leads, and when no lead matches", async () => {
    leadsPage = () => Promise.resolve(res(pageOf([])));
    render(<TelecallerLeadTable basePath="/telecaller/leads" />);
    expect(await screen.findByText("No leads are assigned to you yet.")).toBeTruthy();
    cleanup();
    search = "priority=cold";
    render(<TelecallerLeadTable basePath="/telecaller/leads" />);
    expect(await screen.findByText("No leads match these filters.")).toBeTruthy();
  });

  it("offers a retry when the list fails to load", async () => {
    leadsPage = () => Promise.resolve(res({ detail: "boom" }, 500));
    render(<TelecallerLeadTable basePath="/telecaller/leads" />);
    expect((await screen.findByRole("alert")).textContent).toBe("Unable to load leads.");
    leadsPage = () => Promise.resolve(res(pageOf([lead("3")])));
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("link", { name: "Lead 3" })).toBeTruthy();
  });

  it("ignores filter values the API would refuse (QA-02), so a hand-edited URL still lists leads", async () => {
    search = "priority=urgent&product_id=not-a-uuid&campaign_id=c1x&status=qualified";
    render(<TelecallerLeadTable basePath="/telecaller/leads" />);
    await screen.findByRole("link", { name: "Lead 1" });
    expect(Object.fromEntries(new URLSearchParams(leadCalls()[0].split("?")[1]))).toEqual({ status: "qualified", limit: "50", offset: "0" });
  });

  it("filters by a due follow-up (tel-011 F9) and ignores an unknown value", async () => {
    search = "follow_up=today";
    render(<TelecallerLeadTable basePath="/telecaller/leads" />);
    await screen.findByRole("link", { name: "Lead 1" });
    expect(Object.fromEntries(new URLSearchParams(leadCalls()[0].split("?")[1]))).toEqual({ follow_up: "today", limit: "50", offset: "0" });
    fireEvent.change(screen.getByLabelText("Due follow-up"), { target: { value: "overdue" } });
    expect(pushedQuery().get("follow_up")).toBe("overdue");
    cleanup();
    search = "follow_up=soon";
    render(<TelecallerLeadTable basePath="/telecaller/leads" />);
    await screen.findByRole("link", { name: "Lead 1" });
    expect(Object.fromEntries(new URLSearchParams(leadCalls().at(-1)!.split("?")[1]))).toEqual({ limit: "50", offset: "0" });
  });

  it("marks a lead that is with the counselor and styles the name as a link (QA-01, QA-04)", async () => {
    leadsPage = () => Promise.resolve(res(pageOf([lead("9", { counselor: { id: "c1", full_name: "Kiran" } })])));
    render(<TelecallerLeadTable basePath="/telecaller/leads" />);
    const link = await screen.findByRole("link", { name: "Lead 9" });
    expect(link.style.textDecoration).toBe("underline");
    expect((link.closest("tr") as HTMLElement).textContent).toContain("With counselor");
  });

  it("pages with Previous / Next through the URL", async () => {
    leadsPage = () => Promise.resolve(res(pageOf([lead("1")], 120, 50)));
    search = "offset=50";
    render(<TelecallerLeadTable basePath="/telecaller/leads" />);
    expect(await screen.findByText("Showing 51–51 of 120")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(pushedQuery().get("offset")).toBe("100");
    fireEvent.click(screen.getByRole("button", { name: "Previous page" }));
    expect(pushedQuery().get("offset")).toBeNull();
  });
});
