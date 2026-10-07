import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import TelecallerPerformancePanel from "@/components/TelecallerPerformancePanel";
import {
  PERFORMANCE_UNAVAILABLE, performanceError, performanceParams, performanceQuery, sortHref, type Performance, type PerformanceRow,
} from "@/lib/telecallerPerformance";

afterEach(cleanup);

const BASE = "/telecaller/manager/performance";
const row = (over: Partial<PerformanceRow>): PerformanceRow => ({
  user_id: "u1", full_name: "Asha", team: "IT", active: true, status: "Active",
  leads: 4, calls: 80, connected: 50, qualified: 6, appointments: 3, conversions: 1, ...over,
});
const data = (over: Partial<Performance> = {}): Performance => ({
  date_from: "2026-09-01", date_to: "2026-09-30", team: null, sort: "calls", dir: "desc", teams: ["it", "overseas"],
  items: [row({}), row({ user_id: "u2", full_name: "Bala", active: false, status: "Inactive", leads: 1, calls: 20, connected: 9, qualified: 0, appointments: 0, conversions: 0 })],
  totals: { leads: 5, calls: 100, connected: 59, qualified: 6, appointments: 3, conversions: 1 }, ...over,
});
const panel = (over: Partial<Parameters<typeof TelecallerPerformancePanel>[0]> = {}) =>
  render(<TelecallerPerformancePanel data={data()} params={{}} base={BASE} teams={["it", "overseas"]} today="2026-10-07" {...over} />);

describe("telecallerPerformance lib (tel-023)", () => {
  it("passes on only well-formed parameters", () => {
    expect(performanceParams({ date_from: "2026-09-01", date_to: "2026-02-30", team: "school", sort: "email", dir: "up" }))
      .toEqual({ date_from: "2026-09-01", date_to: undefined, team: undefined, sort: undefined, dir: undefined });
    expect(performanceParams({ team: "overseas", sort: "conversions", dir: "asc" })).toMatchObject({ team: "overseas", sort: "conversions", dir: "asc" });
    expect(performanceQuery({ date_from: "2026-09-01", team: undefined, sort: "calls" })).toBe("?date_from=2026-09-01&sort=calls");
    expect(performanceQuery({})).toBe("");
  });

  it("flips the current column and starts another high-to-low (names A-Z), keeping the range and team", () => {
    const d = data({ team: "it" });
    expect(sortHref(BASE, d, "calls")).toBe(`${BASE}?date_from=2026-09-01&date_to=2026-09-30&team=it&sort=calls&dir=asc`);
    expect(sortHref(BASE, d, "leads")).toContain("sort=leads&dir=desc");
    expect(sortHref(BASE, d, "name")).toContain("sort=name&dir=asc");
  });

  it("shows the API's sentence for a range rule and a generic note otherwise", () => {
    expect(performanceError({ status: 422, message: "The range can't be longer than 366 days" })).toBe("The range can't be longer than 366 days");
    expect(performanceError({ status: 500, message: "boom" })).toBe(PERFORMANCE_UNAVAILABLE);
    expect(performanceError(new TypeError("fetch failed"))).toBe(PERFORMANCE_UNAVAILABLE);
  });
});

describe("TelecallerPerformancePanel (tel-023 §16)", () => {
  it("lays out one row per telecaller with the six figures and a Total row", () => {
    panel({ activityBase: "/telecaller/manager/team" });
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent?.replace(/[↑↓↕]/g, "").trim()))
      .toEqual(["Telecaller", "Team", "Leads", "Calls", "Connected", "Qualified", "Appointments", "Conversions"]);
    const [, first, second, total] = within(table).getAllByRole("row");
    expect(within(first).getAllByRole("cell").map((c) => c.textContent)).toEqual(["IT", "4", "80", "50", "6", "3", "1"]);
    expect(within(second).getByText("Inactive")).toBeInTheDocument();
    expect(within(total).getByRole("rowheader")).toHaveTextContent("Total");
    expect(within(total).getAllByRole("cell").map((c) => c.textContent)).toEqual(["", "5", "100", "59", "6", "3", "1"]);
  });

  it("links names to the telecaller's activity for managers only (PF1)", () => {
    panel({ activityBase: "/telecaller/manager/team" });
    expect(screen.getByRole("link", { name: "Asha" })).toHaveAttribute("href", "/telecaller/manager/team/u1/activity?date=2026-09-30");
    cleanup();
    panel({ teams: [] });
    expect(screen.queryByRole("link", { name: "Asha" })).toBeNull();
    expect(screen.getByRole("rowheader", { name: "Asha" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Team")).toBeNull(); // a division admin has one team: no picker
  });

  it("marks the sorted column and offers sort links on every other", () => {
    panel();
    const calls = screen.getByRole("columnheader", { name: /Calls/ });
    expect(calls).toHaveAttribute("aria-sort", "descending");
    expect(within(calls).getByRole("link")).toHaveAttribute("href", expect.stringContaining("sort=calls&dir=asc"));
    expect(screen.getByRole("columnheader", { name: /Leads/ })).toHaveAttribute("aria-sort", "none");
  });

  it("keeps the range, team and sort in the GET form, and offers the CSV for the same view", () => {
    panel({ params: { sort: "leads", dir: "asc" } });
    expect(screen.getByLabelText("From")).toHaveValue("2026-09-01");
    expect(screen.getByLabelText("To")).toHaveAttribute("max", "2026-10-07");
    expect(screen.getByLabelText("Team")).toHaveValue("");
    const form = screen.getByLabelText("From").closest("form")!;
    expect(form).toHaveAttribute("action", BASE);
    expect(form.querySelector('input[name="sort"]')).toHaveValue("leads");
    expect(screen.getByRole("button", { name: "Download CSV" })).toBeInTheDocument();
  });

  it("shows an empty scope and a refused range", () => {
    panel({ data: data({ items: [] }) });
    expect(screen.getByRole("status")).toHaveTextContent("No telecallers in your scope yet.");
    expect(screen.queryByRole("button", { name: "Download CSV" })).toBeNull();
    cleanup();
    panel({ data: null, error: "The range can't end in the future", params: { date_from: "2026-10-01", date_to: "2026-10-09" } });
    expect(screen.getByRole("alert")).toHaveTextContent("The range can't end in the future");
    expect(screen.getByLabelText("To")).toHaveValue("2026-10-09");
  });
});
