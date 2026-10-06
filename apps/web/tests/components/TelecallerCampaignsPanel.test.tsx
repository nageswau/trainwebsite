import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import TelecallerCampaignsPanel from "@/components/TelecallerCampaignsPanel";
import { activeProducts, campaignDates } from "@/lib/telecallerCatalogue";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const page = (items: unknown[]) => ({ items, total: items.length, limit: 100, offset: 0 });
const cyber = { id: "p1", group: "it", name: "Cyber Security", team: "it", program: null, active: true, sort_order: 3 };
const uk = { id: "p2", group: "overseas", name: "UK", team: "overseas", program: null, active: true, sort_order: 6 };
const sep = {
  id: "c1", name: "Sep 2026 Cyber Security", source: "instagram", product: { id: "p1", name: "Cyber Security", group: "it", active: true },
  start_date: "2026-09-01", end_date: "2026-09-30", active: true,
};
const orphan = { ...sep, id: "c2", name: "Old Dubai push", product: { id: "p9", name: "Dubai", group: "overseas", active: false }, end_date: null };

type Call = { url: string; init?: RequestInit };
function serve(campaigns: unknown, products: unknown[] = [cyber, uk], onWrite?: (call: Call) => Response) {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const call = { url: String(url), init };
    calls.push(call);
    if (init?.method) return Promise.resolve(onWrite ? onWrite(call) : res({}));
    return Promise.resolve(String(url).includes("/telecaller/products") ? res(page(products)) : res(campaigns));
  }));
  return calls;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("campaignDates", () => {
  it("reads date-only values without shifting the day", () => {
    expect(campaignDates({ start_date: "2026-09-01", end_date: "2026-09-30" })).toMatch(/^01 Sept? 2026 – 30 Sept? 2026$/);
    expect(campaignDates({ start_date: "2026-09-01", end_date: null })).toMatch(/^From 01 Sep/);
  });
});

// QA-01: the picker must reach every active product, not only the first page of 100.
describe("activeProducts", () => {
  it("follows the pages until the total is read", async () => {
    const make = (n: number, from: number) => Array.from({ length: n }, (_, i) => ({ ...cyber, id: `p${from + i}`, name: `P${from + i}` }));
    const fetchMock = vi.fn((url: string) => {
      const offset = Number(new URL(url, "http://x").searchParams.get("offset") ?? 0);
      return Promise.resolve(res({ items: offset === 0 ? make(100, 0) : make(5, 100), total: 105, limit: 100, offset }));
    });
    vi.stubGlobal("fetch", fetchMock);
    expect((await activeProducts()).length).toBe(105);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

describe("TelecallerCampaignsPanel (tel-002)", () => {
  it("lists campaigns with source label, product and dates; a deactivated product is flagged", async () => {
    serve(page([sep, orphan]));
    render(<TelecallerCampaignsPanel />);
    const row = (await screen.findByText("Sep 2026 Cyber Security")).closest("tr")!;
    expect(within(row).getByText("Instagram")).toBeInTheDocument();
    expect(within(row).getByText("Cyber Security")).toBeInTheDocument();
    expect(within(screen.getByText("Old Dubai push").closest("tr")!).getByText("Product inactive")).toBeInTheDocument();
  });

  it("shows empty and error states", async () => {
    serve(page([]));
    render(<TelecallerCampaignsPanel />);
    expect(await screen.findByText("No campaigns yet. Use the Create campaign form to add the first one.")).toBeInTheDocument();
    cleanup();
    serve({ detail: "x" });
    render(<TelecallerCampaignsPanel />);
    expect(await screen.findByText("Unable to load campaigns.")).toBeInTheDocument();
  });

  it("offers the 13 sources and only active products, grouped", async () => {
    serve(page([]));
    render(<TelecallerCampaignsPanel />);
    const source = screen.getByLabelText("Source (required)");
    expect(within(source).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Choose a source", "Instagram", "Facebook", "Google", "Website", "WhatsApp", "Walk-in", "College", "School", "Agent", "Referral", "Exhibition/Event", "BDM", "Other",
    ]);
    const product = await screen.findByLabelText("Product (required)");
    expect(await within(product).findByRole("option", { name: "Cyber Security" })).toBeInTheDocument();
    expect(within(product).getByRole("group", { name: "Overseas Education" })).toBeInTheDocument();
  });

  it("says when no active product exists and disables create", async () => {
    serve(page([]), []);
    render(<TelecallerCampaignsPanel />);
    expect(await screen.findByText(/No active product/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create campaign" })).toBeDisabled();
  });

  it("refuses an end date before the start date in the browser, then creates", async () => {
    const calls = serve(page([]), [cyber, uk], () => res(sep, 201));
    render(<TelecallerCampaignsPanel />);
    await screen.findByRole("option", { name: "Cyber Security" });
    fireEvent.change(screen.getByLabelText("Campaign name (required)"), { target: { value: "Sep 2026 Cyber Security" } });
    fireEvent.change(screen.getByLabelText("Source (required)"), { target: { value: "instagram" } });
    fireEvent.change(screen.getByLabelText("Product (required)"), { target: { value: "p1" } });
    fireEvent.change(screen.getByLabelText("Start date (required)"), { target: { value: "2026-09-30" } });
    fireEvent.change(screen.getByLabelText("End date"), { target: { value: "2026-09-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Create campaign" }));
    expect(await screen.findByText("End date cannot be before the start date")).toBeInTheDocument();
    expect(calls.some((c) => c.init?.method === "POST")).toBe(false);
    fireEvent.change(screen.getByLabelText("Start date (required)"), { target: { value: "2026-09-01" } });
    fireEvent.change(screen.getByLabelText("End date"), { target: { value: "2026-09-30" } });
    fireEvent.click(screen.getByRole("button", { name: "Create campaign" }));
    expect(await screen.findByText("Created Sep 2026 Cyber Security.")).toBeInTheDocument();
    expect(JSON.parse(String(calls.find((c) => c.init?.method === "POST")!.init!.body))).toEqual({
      name: "Sep 2026 Cyber Security", source: "instagram", product_id: "p1", start_date: "2026-09-01", end_date: "2026-09-30",
    });
  });

  it("edits a campaign whose product was deactivated without forcing a new product", async () => {
    const calls = serve(page([orphan]), [cyber, uk], () => res({ ...orphan, name: "Dubai push" }));
    render(<TelecallerCampaignsPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit Old Dubai push" }));
    const product = screen.getByLabelText("Campaign product (required)");
    expect(product).toHaveValue("p9");
    expect(within(product).getByRole("option", { name: "Dubai (inactive)" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Campaign name (required)", { selector: "#camp-name-c2" }), { target: { value: "Dubai push" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Saved Dubai push.")).toBeInTheDocument();
    expect(JSON.parse(String(calls.find((c) => c.init?.method === "PATCH")!.init!.body))).toEqual({
      name: "Dubai push", source: "instagram", product_id: "p9", start_date: "2026-09-01", end_date: null,
    });
  });

  // QA-02: on tablets and phones the list comes first, so its card offers a jump to the create form (the tel-001 idiom).
  it("offers a jump link that moves focus to the create form", () => {
    serve(page([]));
    render(<TelecallerCampaignsPanel />);
    const jump = screen.getByRole("link", { name: "Create campaign" });
    expect(jump).toHaveAttribute("href", "#camp-name");
    fireEvent.click(jump);
    expect(screen.getByLabelText("Campaign name (required)")).toHaveFocus();
  });

  it("deactivates after confirm and reactivates directly", async () => {
    const calls = serve(page([sep, { ...orphan, active: false }]));
    render(<TelecallerCampaignsPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Deactivate Sep 2026 Cyber Security" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm deactivate" }));
    expect(await screen.findByText("Deactivated Sep 2026 Cyber Security.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reactivate Old Dubai push" }));
    expect(await screen.findByText("Reactivated Old Dubai push.")).toBeInTheDocument();
    expect(calls.filter((c) => c.init?.method === "PATCH").map((c) => JSON.parse(String(c.init!.body)))).toEqual([{ active: false }, { active: true }]);
  });
});
