import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import MarketingBudgetForm from "@/components/MarketingBudgetForm";
import MarketingDashboard from "@/components/MarketingDashboard";
import type { MarketingChannel, MarketingMonth } from "@/lib/marketing";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh }) }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const channel = (key: string, label: string, over: Partial<MarketingChannel> = {}): MarketingChannel => ({
  channel: key, label, budget: null, spend: "0.00", leads: 0, qualified: 0, customers: 0, conversion: null, revenue: "0.00", roi: null, ...over,
});
const data = (over: Partial<MarketingMonth> = {}): MarketingMonth => ({
  month: "2026-09", current_month: "2026-10", money_visible: true,
  channels: [
    channel("instagram", "Instagram", { budget: "100000.00", spend: "85000.00", leads: 500, qualified: 120, customers: 35, conversion: 7, revenue: "500000.00", roi: 488.2 }),
    channel("google", "Google", { budget: "0.00" }),
    channel("school", "School", { leads: 250, qualified: 40, customers: 30, conversion: 12 }),
  ],
  totals: { budget: "100000.00", spend: "85000.00", leads: 750, qualified: 160, customers: 65, conversion: 8.7, revenue: "500000.00", roi: 488.2 },
  groups: { social: 500, website: 0, school: 250, college: 0, agent: 0, influencer: null, events: 0 },
  campaigns: [{ id: "c1", name: "Instagram → Cyber Security → September 2026", channel: "instagram", label: "Instagram", active: true, leads: 320, qualified: 80, customers: 20 }],
  budgets_updated_at: "2026-09-02T10:00:00Z", budgets_updated_by: { id: "u", full_name: "Asha Accountant" },
  ...over,
});
const noMoney = (): MarketingMonth => {
  const strip = <T extends object>(f: T) => ({ ...f, budget: null, spend: null, revenue: null, roi: null });
  const d = data();
  return { ...d, money_visible: false, channels: d.channels.map(strip), totals: strip(d.totals), budgets_updated_at: null, budgets_updated_by: null };
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  refresh.mockReset();
});

describe("MarketingDashboard (mgmt-012 §10, §15)", () => {
  it("shows the source's ROI row per channel: budget, spent, leads, customers, revenue, ROI", () => {
    render(<MarketingDashboard data={data()} />);
    const table = screen.getByRole("table", { name: "Marketing ROI by channel, September 2026" });
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(
      ["Channel", "Budget", "Spent", "Leads", "Qualified", "Customers", "Conversion", "Revenue", "ROI"],
    );
    const ig = within(table).getByRole("row", { name: /^Instagram/ });
    for (const text of ["₹1,00,000.00", "₹85,000.00", "500", "35", "7%", "₹5,00,000.00", "488.2%"]) expect(ig.textContent).toContain(text);
    expect(within(table).getByRole("row", { name: /^Google/ }).textContent).toContain("₹0.00"); // a budget of nothing
    const school = within(table).getByRole("row", { name: /^School/ }).textContent ?? "";
    expect(school).toContain("Not set"); // no budget
    expect(school).toContain("—"); // zero spend: no ROI
    expect(within(table).getByRole("row", { name: /^Total/ }).textContent).toContain("750");
  });

  it("lists the §15 figures, with influencer leads not tracked", () => {
    render(<MarketingDashboard data={data()} />);
    const tiles = screen.getByRole("list", { name: "Marketing figures, September 2026" }).textContent ?? "";
    for (const text of ["Marketing budget", "Marketing spend", "Leads", "Qualified leads", "Campaigns", "Social media leads", "Website leads", "School leads",
      "College leads", "Agent leads", "Influencer leads", "Not tracked", "Events", "Conversion", "8.7%", "Revenue", "ROI", "488.2%"]) {
      expect(tiles).toContain(text);
    }
  });

  it("gives super_admin the lead figures with no money anywhere (MK11)", () => {
    render(<MarketingDashboard data={noMoney()} />);
    const tiles = screen.getByRole("list", { name: "Marketing figures, September 2026" }).textContent ?? "";
    for (const text of ["Marketing budget", "Marketing spend", "Revenue", "ROI", "₹"]) expect(tiles).not.toContain(text);
    expect(tiles).toContain("Qualified leads");
    const table = screen.getByRole("table", { name: "Leads by channel, September 2026" });
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Channel", "Leads", "Qualified", "Customers", "Conversion"]);
    expect(screen.getByText(/partners and the accountant only/)).toBeTruthy();
  });

  it("lists the campaigns, or says none ran", () => {
    render(<MarketingDashboard data={data()} />);
    const campaigns = screen.getByRole("table", { name: "Campaigns, September 2026" });
    expect(within(campaigns).getByText("Instagram → Cyber Security → September 2026")).toBeTruthy();
    cleanup();
    render(<MarketingDashboard data={data({ campaigns: [] })} />);
    expect(screen.getByText("No campaign ran or brought leads in September 2026.")).toBeTruthy();
  });
});

describe("MarketingBudgetForm (mgmt-012 MK4)", () => {
  it("starts from the saved budgets, sends the filled channels and refreshes", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res(data()));
    vi.stubGlobal("fetch", fetchMock);
    render(<MarketingBudgetForm data={data()} />);
    expect((screen.getByLabelText("Instagram budget (₹)") as HTMLInputElement).value).toBe("100000.00");
    expect((screen.getByLabelText("School budget (₹)") as HTMLInputElement).value).toBe("");
    fireEvent.change(screen.getByLabelText("School budget (₹)"), { target: { value: "70000" } });
    fireEvent.change(screen.getByLabelText("Google budget (₹)"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save September 2026 budgets" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/management/marketing/budgets?month=2026-09");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body)).toEqual({ budgets: [{ channel: "instagram", amount: "100000.00" }, { channel: "school", amount: "70000" }] });
    expect(screen.getByRole("status").textContent).toBe("Budgets for September 2026 saved.");
  });

  it("puts a 422 on its channel and keeps what was typed", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail: [{ loc: ["body", "budgets", 1, "amount"], msg: "An amount can't be negative" }] }, 422)));
    render(<MarketingBudgetForm data={data()} />);
    fireEvent.change(screen.getByLabelText("Google budget (₹)"), { target: { value: "-5" } });
    fireEvent.click(screen.getByRole("button", { name: "Save September 2026 budgets" }));
    const input = screen.getByLabelText("Google budget (₹)") as HTMLInputElement;
    await waitFor(() => expect(input.getAttribute("aria-invalid")).toBe("true"));
    expect(input.value).toBe("-5");
    expect(document.getElementById(input.getAttribute("aria-describedby") ?? "")?.textContent).toBe("An amount can't be negative");
    expect(screen.getByRole("alert").textContent).toBe("Check the highlighted budgets and save again.");
    expect(refresh).not.toHaveBeenCalled();
  });

  it("sends one request for a double click", async () => {
    let finish: (r: Response) => void = () => {};
    const fetchMock = vi.fn().mockReturnValue(new Promise<Response>((resolve) => (finish = resolve)));
    vi.stubGlobal("fetch", fetchMock);
    render(<MarketingBudgetForm data={data()} />);
    const save = screen.getByRole("button", { name: "Save September 2026 budgets" });
    fireEvent.click(save);
    fireEvent.click(save);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    finish(res(data()));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
  });
});
