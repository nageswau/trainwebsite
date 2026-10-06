import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import TelecallerTargetsPanel from "@/components/TelecallerTargetsPanel";
import { earliestDaily, istToday, monthOptions } from "@/lib/telecallerTargets";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const page = (items: unknown[], total = items.length) => ({ items, total, limit: 50, offset: 0 });
const values = (overrides: Record<string, [number | null, string | null]> = {}) =>
  ["calls", "connected_calls", "qualified_leads", "follow_ups", "counselling_appointments", "conversions"].map((kpi) => ({
    kpi, value: overrides[kpi]?.[0] ?? null, source: overrides[kpi]?.[1] ?? null,
  }));
const effective = (daily = values(), monthly = values()) => ({ date: "2026-10-06", month: "2026-10-01", team: "it", user: null, daily, monthly });
const history = {
  id: "t1", scope: "team", team: "it", user: null, period: "daily", kpi: "calls", value: 80, effective_from: "2026-10-07",
  set_by: { id: "m1", full_name: "Mona Manager" }, updated_at: "2026-10-06T05:00:00Z",
};
const ravi = { id: "u1", full_name: "Ravi Telecaller", email: "r@x", phone: null, active: true, team: "it", employee_id: "E1" };

type Call = { url: string; init?: RequestInit };
function serve({ eff = effective(), rows = [history] as unknown[], total = rows.length, onPost }: { eff?: unknown; rows?: unknown[]; total?: number; onPost?: (body: Record<string, unknown>) => Response } = {}) {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const call = { url: String(url), init };
    calls.push(call);
    if (init?.method === "POST") return Promise.resolve(onPost ? onPost(JSON.parse(String(init.body))) : res({}));
    if (call.url.includes("/targets/effective")) return Promise.resolve(res(eff));
    if (call.url.includes("/manager/team")) return Promise.resolve(res(page([ravi, { ...ravi, id: "u2", full_name: "Old Inactive", active: false }])));
    return Promise.resolve(res(page(rows, total)));
  }));
  return calls;
}
const posts = (calls: Call[]) => calls.filter((c) => c.init?.method === "POST").map((c) => JSON.parse(String(c.init!.body)));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("target dates (G2)", () => {
  it("reads today in IST and offers tomorrow / the next twelve months", () => {
    expect(istToday(new Date("2026-10-06T20:00:00Z"))).toBe("2026-10-07"); // 01:30 IST next day
    expect(earliestDaily("2026-12-31")).toBe("2027-01-01");
    const months = monthOptions("2026-10-31");
    expect(months).toHaveLength(12);
    expect(months[0]).toEqual({ value: "2026-11-01", label: "November 2026" });
    expect(months[11].value).toBe("2027-10-01");
  });
});

describe("TelecallerTargetsPanel (tel-022)", () => {
  it("shows the IT team default in effect and its history", async () => {
    const calls = serve({ eff: effective(values({ calls: [80, "team"] }), values({ conversions: [60, "team"] })) });
    render(<TelecallerTargetsPanel />);
    const inEffect = await screen.findByRole("region", { name: "Targets in effect" });
    const calls_ = within(inEffect).getByText("Calls").closest("tr")!;
    expect(within(calls_).getByText("80")).toBeInTheDocument();
    expect(within(within(inEffect).getByText("Conversions").closest("tr")!).getByText("60")).toBeInTheDocument();
    const historyTable = await screen.findByRole("region", { name: "Target history" });
    expect(within(historyTable).getByText("Mona Manager")).toBeInTheDocument();
    expect(calls.some((c) => c.url.includes("/targets/effective?team=it"))).toBe(true);
    expect(calls.some((c) => c.url.includes("scope=team") && c.url.includes("team=it"))).toBe(true);
  });

  it("saves only the filled KPIs for the team, from the chosen date, and reloads", async () => {
    const calls = serve({ onPost: () => res({}) });
    render(<TelecallerTargetsPanel />);
    await screen.findByRole("region", { name: "Targets in effect" });
    const save = screen.getByRole("button", { name: "Save targets" });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Calls target"), { target: { value: "80" } });
    fireEvent.change(screen.getByLabelText("Conversions target"), { target: { value: "0" } });
    expect(screen.getByLabelText("Starts on")).toHaveValue(earliestDaily(istToday()));
    fireEvent.click(save);
    await screen.findByText(/Saved 2 targets/);
    expect(posts(calls)).toEqual([{ scope: "team", team: "it", period: "daily", effective_from: earliestDaily(istToday()), values: { calls: 80, conversions: 0 } }]);
    await waitFor(() => expect(calls.filter((c) => c.url.includes("/targets/effective")).length).toBe(2));
    expect(screen.getByLabelText("Calls target")).toHaveValue(null);
  });

  it("monthly targets start on a chosen 1st of month", async () => {
    const calls = serve();
    render(<TelecallerTargetsPanel />);
    await screen.findByRole("region", { name: "Targets in effect" });
    fireEvent.click(screen.getByLabelText("Monthly"));
    const month = monthOptions(istToday())[2].value;
    fireEvent.change(screen.getByLabelText("Starts on"), { target: { value: month } });
    fireEvent.change(screen.getByLabelText("Calls target"), { target: { value: "1500" } });
    fireEvent.click(screen.getByRole("button", { name: "Save targets" }));
    await waitFor(() => expect(posts(calls)).toEqual([{ scope: "team", team: "it", period: "monthly", effective_from: month, values: { calls: 1500 } }]));
  });

  it("a telecaller override can fall back to the team default (null)", async () => {
    const calls = serve({ eff: { ...effective(values({ calls: [90, "user"], follow_ups: [25, "team"] })), user: { id: "u1", full_name: "Ravi Telecaller" } } });
    render(<TelecallerTargetsPanel />);
    await screen.findByRole("region", { name: "Targets in effect" });
    fireEvent.change(screen.getByLabelText("Set targets for"), { target: { value: "user" } });
    expect(screen.queryByRole("region", { name: "Targets in effect" })).not.toBeInTheDocument();
    expect(screen.getByText("Choose a telecaller to see and set their targets.")).toBeInTheDocument();
    const picker = screen.getByRole("combobox", { name: /Telecaller/ });
    fireEvent.focus(picker);
    fireEvent.change(picker, { target: { value: "Ra" } });
    fireEvent.click(await screen.findByRole("option", { name: /Ravi Telecaller/ }));
    expect(screen.queryByRole("option", { name: /Old Inactive/ })).not.toBeInTheDocument();
    const inEffect = await screen.findByRole("region", { name: "Targets in effect" });
    expect(within(within(inEffect).getByText("Calls").closest("tr")!).getByText(/Override/)).toBeInTheDocument();
    expect(within(within(inEffect).getByText("Follow-ups").closest("tr")!).getByText(/Team default/)).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Use team default for Calls"));
    expect(screen.getByLabelText("Calls target")).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Qualified leads target"), { target: { value: "15" } });
    fireEvent.click(screen.getByRole("button", { name: "Save targets" }));
    await waitFor(() => expect(posts(calls)[0]).toMatchObject({ scope: "user", user_id: "u1", period: "daily", values: { calls: null, qualified_leads: 15 } }));
    expect(calls.some((c) => c.url.includes("/targets/effective?user_id=u1"))).toBe(true);
    expect(calls.some((c) => c.url.includes("user_id=u1") && c.url.includes("/targets?"))).toBe(true);
  });

  it("shows the API's sentence when a save is refused and keeps the entry", async () => {
    serve({ onPost: () => res({ detail: "Daily targets can start on 07 Oct 2026 or later" }, 422) });
    render(<TelecallerTargetsPanel />);
    await screen.findByRole("region", { name: "Targets in effect" });
    fireEvent.change(screen.getByLabelText("Calls target"), { target: { value: "80" } });
    fireEvent.click(screen.getByRole("button", { name: "Save targets" }));
    expect(await screen.findByText("Daily targets can start on 07 Oct 2026 or later")).toBeInTheDocument();
    expect(screen.getByLabelText("Calls target")).toHaveValue(80);
  });

  it("refuses a negative number in the browser too", async () => {
    const calls = serve();
    render(<TelecallerTargetsPanel />);
    await screen.findByRole("region", { name: "Targets in effect" });
    fireEvent.change(screen.getByLabelText("Calls target"), { target: { value: "-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Save targets" }));
    expect(await screen.findByText("Calls must be a whole number from 0 to 100000.")).toBeInTheDocument();
    expect(posts(calls)).toEqual([]);
  });

  it("empty history and a load failure with Retry", async () => {
    serve({ rows: [] });
    render(<TelecallerTargetsPanel />);
    expect(await screen.findByText("No targets set yet.")).toBeInTheDocument();
    cleanup();
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "boom" }, 500))));
    render(<TelecallerTargetsPanel />);
    expect(await screen.findByText("Unable to load targets.")).toBeInTheDocument();
    serve();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("region", { name: "Targets in effect" })).toBeInTheDocument();
  });

  it("pages through a long history", async () => {
    const calls = serve({ rows: [history], total: 120 });
    render(<TelecallerTargetsPanel />);
    await screen.findByRole("region", { name: "Target history" });
    expect(screen.getByText("Showing 1–1 of 120")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    await waitFor(() => expect(calls.some((c) => c.url.includes("offset=50"))).toBe(true));
  });
});
