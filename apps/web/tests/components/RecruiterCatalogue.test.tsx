import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import RecruiterCampaignsPanel from "@/components/RecruiterCampaignsPanel";
import RecruiterCatalogueValuesPanel from "@/components/RecruiterCatalogueValuesPanel";
import { TABS, VALUE_TABS, isTab } from "@/lib/recruiterCatalogue";

const nav = vi.hoisted(() => ({ params: new URLSearchParams(), push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: nav.push }), usePathname: () => "/recruiter/manager/catalogue/lead-sources", useSearchParams: () => nav.params }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const page = (items: unknown[]) => ({ items, total: items.length, limit: 100, offset: 0 });
const linkedin = { id: "s1", name: "LinkedIn", active: true, sort_order: 1 };
const fairs = { id: "s2", name: "Job fairs", active: false, sort_order: 3 };
const q4 = { id: "c1", name: "Q4 IT hiring push", lead_source: { id: "s1", name: "LinkedIn", active: true }, start_date: "2026-10-01", end_date: "2026-12-31", active: true };

type Call = { url: string; init?: RequestInit };
function serve(read: (url: string) => Response, onWrite: (call: Call) => Response = () => res({})) {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const call = { url: String(url), init };
    calls.push(call);
    return Promise.resolve(init?.method ? onWrite(call) : read(String(url)));
  }));
  return calls;
}
const writes = (calls: Call[]) => calls.filter((c) => c.init?.method);

afterEach(() => {
  cleanup();
  nav.params = new URLSearchParams();
  nav.push.mockReset();
  vi.unstubAllGlobals();
});

describe("tabs", () => {
  it("offers the six lists and campaigns, and nothing else", () => {
    expect(Object.keys(TABS)).toEqual(["lead-sources", "candidate-sources", "industries", "company-sizes", "contact-roles", "job-categories", "campaigns"]);
    expect(isTab("campaigns") && isTab("industries")).toBe(true);
    expect(isTab("colours") || isTab("toString")).toBe(false);
  });

  it("speaks to the manager, not in evidence references (QA-01)", () => {
    for (const tab of Object.values(TABS)) expect(tab.intro).not.toMatch(/EVID|§|starts empty/);
  });
});

describe("RecruiterCatalogueValuesPanel", () => {
  it("lists values with their status and reads the list's endpoint", async () => {
    const calls = serve(() => res(page([linkedin, fairs])));
    render(<RecruiterCatalogueValuesPanel kind="lead-sources" />);
    const table = await screen.findByRole("region", { name: "Lead sources" });
    expect(within(table).getByText("LinkedIn")).toBeTruthy();
    expect(within(table).getByText("Inactive")).toBeTruthy();
    expect(calls[0].url).toBe("/api/v1/recruiter/catalogue/lead-sources?limit=100&offset=0");
    expect(screen.getByRole("button", { name: "Reactivate Job fairs" })).toBeTruthy();
  });

  it("shows the empty state for an empty list (industries start empty)", async () => {
    serve(() => res(page([])));
    render(<RecruiterCatalogueValuesPanel kind="industries" />);
    expect(await screen.findByText("No industries yet.")).toBeTruthy();
  });

  it("shows an error with Retry when the list cannot load", async () => {
    let fail = true;
    serve(() => (fail ? res({ detail: "boom" }, 500) : res(page([linkedin]))));
    render(<RecruiterCatalogueValuesPanel kind="lead-sources" />);
    expect(await screen.findByText("Unable to load lead sources.")).toBeTruthy();
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("LinkedIn")).toBeTruthy();
  });

  it("creates a value once even on a double submit, then reloads", async () => {
    const calls = serve(() => res(page([linkedin])), () => res({ ...linkedin, id: "n1", name: "Naukri" }, 201));
    render(<RecruiterCatalogueValuesPanel kind="lead-sources" />);
    await screen.findByText("LinkedIn");
    fireEvent.change(screen.getByLabelText("Lead source name (required)"), { target: { value: "  Naukri " } });
    const form = screen.getByRole("button", { name: "Add lead source" }).closest("form")!;
    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(await screen.findByText("Added Naukri.")).toBeTruthy();
    expect(writes(calls)).toHaveLength(1);
    expect(writes(calls)[0]).toMatchObject({ url: "/api/v1/recruiter/catalogue/lead-sources", init: { method: "POST", body: JSON.stringify({ name: "Naukri" }) } });
  });

  it("shows the API's duplicate message", async () => {
    serve(() => res(page([linkedin])), () => res({ detail: "A value named “linkedin” already exists in this list" }, 409));
    render(<RecruiterCatalogueValuesPanel kind="lead-sources" />);
    await screen.findByText("LinkedIn");
    fireEvent.change(screen.getByLabelText("Lead source name (required)"), { target: { value: "linkedin" } });
    fireEvent.submit(screen.getByRole("button", { name: "Add lead source" }).closest("form")!);
    expect(await screen.findByText("A value named “linkedin” already exists in this list")).toBeTruthy();
  });

  it("renames inline (Esc cancels) and deactivates after a confirm", async () => {
    const calls = serve(() => res(page([linkedin])));
    render(<RecruiterCatalogueValuesPanel kind="lead-sources" />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit LinkedIn" }));
    const input = screen.getByLabelText("Lead source name (required)", { selector: "#rec-value-name-s1" });
    fireEvent.keyDown(input, { key: "Escape" });
    expect(screen.queryByDisplayValue("LinkedIn")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Edit LinkedIn" }));
    fireEvent.change(screen.getByDisplayValue("LinkedIn"), { target: { value: "LinkedIn Recruiter" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Saved LinkedIn Recruiter.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Deactivate LinkedIn" }));
    expect(writes(calls)).toHaveLength(1); // the confirm comes first
    fireEvent.click(screen.getByRole("button", { name: "Confirm deactivate" }));
    expect(await screen.findByText("Deactivated LinkedIn.")).toBeTruthy();
    expect(writes(calls).map((c) => [c.url, c.init?.method, c.init?.body])).toEqual([
      ["/api/v1/recruiter/catalogue/lead-sources/s1", "PATCH", JSON.stringify({ name: "LinkedIn Recruiter" })],
      ["/api/v1/recruiter/catalogue/lead-sources/s1", "PATCH", JSON.stringify({ active: false })],
    ]);
  });

  it("searches through the URL", async () => {
    serve(() => res(page([linkedin])));
    render(<RecruiterCatalogueValuesPanel kind="lead-sources" />);
    await screen.findByText("LinkedIn");
    fireEvent.change(screen.getByRole("searchbox", { name: "Search lead sources" }), { target: { value: "link" } });
    fireEvent.submit(screen.getByRole("search"));
    expect(nav.push).toHaveBeenCalledWith("/recruiter/manager/catalogue/lead-sources?q=link", { scroll: false });
  });

  it("names each list's form after its noun", () => {
    serve(() => res(page([])));
    for (const kind of Object.keys(VALUE_TABS) as (keyof typeof VALUE_TABS)[]) {
      const { unmount } = render(<RecruiterCatalogueValuesPanel kind={kind} />);
      expect(screen.getByRole("button", { name: `Add ${VALUE_TABS[kind].noun}` })).toBeTruthy();
      unmount();
    }
  });
});

describe("RecruiterCampaignsPanel", () => {
  const reads = (url: string) => (url.includes("/lead-sources") ? res(page([linkedin])) : res(page([q4])));

  it("lists campaigns with their lead source and dates, and offers active lead sources only", async () => {
    const calls = serve(reads);
    render(<RecruiterCampaignsPanel />);
    const table = await screen.findByRole("region", { name: "Campaigns" });
    expect(within(table).getByText("Q4 IT hiring push")).toBeTruthy();
    expect(within(table).getByText(/01 Oct 2026 – 31 Dec 2026/)).toBeTruthy();
    expect(await screen.findByRole("option", { name: "LinkedIn" })).toBeTruthy();
    expect(calls.some((c) => c.url === "/api/v1/recruiter/catalogue/lead-sources?active=true&limit=100&offset=0")).toBe(true);
  });

  it("refuses an end date before the start in the browser, then creates", async () => {
    const calls = serve(reads, () => res(q4, 201));
    render(<RecruiterCampaignsPanel />);
    await screen.findByRole("option", { name: "LinkedIn" });
    fireEvent.change(screen.getByLabelText("Campaign name (required)"), { target: { value: "Q4 IT hiring push" } });
    fireEvent.change(screen.getByLabelText("Lead source (required)"), { target: { value: "s1" } });
    fireEvent.change(screen.getByLabelText("Start date (required)"), { target: { value: "2026-10-01" } });
    fireEvent.change(screen.getByLabelText("End date"), { target: { value: "2026-09-01" } });
    const form = screen.getByRole("button", { name: "Create campaign" }).closest("form")!;
    fireEvent.submit(form);
    expect(await screen.findByText("End date cannot be before the start date")).toBeTruthy();
    expect(writes(calls)).toHaveLength(0);
    fireEvent.change(screen.getByLabelText("End date"), { target: { value: "" } });
    fireEvent.submit(form);
    expect(await screen.findByText("Created Q4 IT hiring push.")).toBeTruthy();
    expect(JSON.parse(String(writes(calls)[0].init?.body))).toEqual({ name: "Q4 IT hiring push", lead_source_id: "s1", start_date: "2026-10-01", end_date: null });
  });

  it("explains an empty lead-source list instead of a dead form", async () => {
    serve((url) => (url.includes("/lead-sources") ? res(page([])) : res(page([]))));
    render(<RecruiterCampaignsPanel />);
    expect(await screen.findByText(/No active lead source/)).toBeTruthy();
    expect((screen.getByRole("button", { name: "Create campaign" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("keeps a since-deactivated lead source when editing", async () => {
    const retired = { ...q4, lead_source: { id: "s9", name: "Cold calling", active: false } };
    serve((url) => (url.includes("/lead-sources") ? res(page([linkedin])) : res(page([retired]))));
    render(<RecruiterCampaignsPanel />);
    expect(await screen.findByText("Lead source inactive")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Edit Q4 IT hiring push" }));
    expect(screen.getByRole("option", { name: "Cold calling (inactive)" })).toBeTruthy();
  });
});
