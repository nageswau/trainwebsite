import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import TelecallerActivityPanel from "@/components/TelecallerActivityPanel";
import TelecallerAppointmentsCard from "@/components/TelecallerAppointmentsCard";
import TelecallerDashboardTiles from "@/components/TelecallerDashboardTiles";
import TelecallerTargetsCard from "@/components/TelecallerTargetsCard";
import { ACTIVITY, activityError, activityUrl, dayParam, type TelecallerActivity } from "@/lib/telecallerMetrics";

afterEach(cleanup);

const TILES = {
  new_leads: 4, calls_today: { done: 65, to_do: 12 }, follow_ups_due: 3, hot_leads: 2, appointments: 1, connected: 40, not_connected: 25,
  converted: 0, overdue: 5, daily_target: { achieved: 65, target: 80 },
};
const KPIS = ["calls", "connected_calls", "qualified_leads", "follow_ups", "counselling_appointments", "conversions"];
const zeros = Object.fromEntries(ACTIVITY.map((a) => [a.key, 0])) as TelecallerActivity["counts"];
const activity = (over: Partial<TelecallerActivity> = {}): TelecallerActivity => ({
  day: "2026-10-06", user: { id: "u1", full_name: "Ravi" }, counts: { ...zeros, calls: 65 },
  targets: KPIS.map((kpi) => ({ kpi, achieved: kpi === "calls" ? 65 : 0, target: kpi === "calls" ? 80 : null })), ...over,
});

describe("TelecallerDashboardTiles (tel-021 §1)", () => {
  it("shows the ten tiles in the source's order with their figures", () => {
    render(<TelecallerDashboardTiles tiles={TILES} />);
    const tiles = within(screen.getByRole("list", { name: "Today at a glance" })).getAllByRole("listitem");
    expect(tiles.map((t) => t.querySelector("span")!.textContent)).toEqual([
      "New Leads", "Calls Today", "Follow-ups Due", "Hot Leads", "Appointments", "Connected", "Not Connected", "Converted", "Overdue", "Daily Target"]);
    expect(within(tiles[1]).getByText("65 / 12")).toBeInTheDocument();
    expect(within(tiles[9]).getByText("65 / 80")).toBeInTheDocument();
    expect(within(tiles[7]).getByText("0")).toBeInTheDocument(); // zeros, never "no data"
  });

  it("says so when the figures could not be loaded", () => {
    render(<TelecallerDashboardTiles tiles={null} />);
    expect(screen.getByText("Today's figures are unavailable right now.")).toBeInTheDocument();
  });
});

describe("TelecallerAppointmentsCard (tel-021 B5)", () => {
  it("lists today's appointments with a link to the lead for counselling", () => {
    render(<TelecallerAppointmentsCard appointments={[
      { kind: "bdm", id: "b1", code: "MR-000001", title: "Govt College", scheduled_at: "2026-10-06T05:30:00Z", status: "scheduled", lead_id: null },
      { kind: "counselling", id: "a1", code: "CAP-000002", title: "Asha", scheduled_at: "2026-10-06T08:30:00Z", status: "confirmed", lead_id: "l1" },
    ]} />);
    const items = within(screen.getByRole("list", { name: "Today's appointments" })).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent(/BDM meeting · Govt College/);
    expect(within(items[1]).getByRole("link", { name: "Asha" })).toHaveAttribute("href", "/telecaller/leads/l1");
  });

  it("handles none and a failed read", () => {
    render(<TelecallerAppointmentsCard appointments={[]} />);
    expect(screen.getByText("No appointments today.")).toBeInTheDocument();
    cleanup();
    render(<TelecallerAppointmentsCard appointments={null} />);
    expect(screen.getByText("Appointments are unavailable right now.")).toBeInTheDocument();
  });
});

describe("TelecallerTargetsCard with achieved figures (tel-021 §15)", () => {
  it("shows achieved / target for today and the month to date", () => {
    const row = (kpi: string, value: number | null) => ({ kpi, value, source: value === null ? null : ("team" as const) });
    const targets = {
      date: "2026-10-06", month: "2026-10-01", team: "it" as const, user: null,
      daily: KPIS.map((k) => row(k, k === "calls" ? 80 : null)), monthly: KPIS.map((k) => row(k, k === "calls" ? 1600 : null)),
    };
    const progress = {
      daily: KPIS.map((kpi) => ({ kpi, achieved: kpi === "calls" ? 65 : 0, target: kpi === "calls" ? 80 : null })),
      monthly: KPIS.map((kpi) => ({ kpi, achieved: kpi === "calls" ? 410 : 0, target: kpi === "calls" ? 1600 : null })),
    };
    render(<TelecallerTargetsCard targets={targets} progress={progress} />);
    const calls = screen.getByText("Calls").closest("tr")!;
    expect(within(calls).getByText("65 / 80")).toBeInTheDocument();
    expect(within(calls).getByText("410 / 1600")).toBeInTheDocument();
    expect(within(screen.getByText("Conversions").closest("tr")!).getAllByText("0 / not set")).toHaveLength(2);
    expect(screen.queryByText(/Achieved figures will appear here/)).not.toBeInTheDocument();
  });
});

describe("TelecallerActivityPanel (tel-021 §14)", () => {
  it("shows the 13 counts and the day's targets, with a date form capped at today", () => {
    render(<TelecallerActivityPanel activity={activity()} day="2026-10-06" today="2026-10-07" />);
    const panel = screen.getByRole("region", { name: "Daily activity" });
    const rows = within(within(panel).getByRole("table", { name: /Activity on/ })).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(13);
    expect(within(rows[1]).getByText("65")).toBeInTheDocument();
    expect(within(panel).getByText("65 / 80")).toBeInTheDocument();
    const input = within(panel).getByLabelText("Day");
    expect(input).toHaveAttribute("max", "2026-10-07");
    expect(input).toHaveValue("2026-10-06");
  });

  it("shows the API's sentence when the day is refused", () => {
    render(<TelecallerActivityPanel activity={null} error="Daily activity can't be shown for a future date" day="2026-10-09" today="2026-10-07" />);
    expect(screen.getByRole("alert")).toHaveTextContent("future date");
  });
});

describe("telecallerMetrics helpers", () => {
  it("passes only a well-formed date and builds the activity URL", () => {
    expect(dayParam("2026-10-06")).toBe("2026-10-06");
    expect(dayParam("06/10/2026")).toBeUndefined();
    expect(dayParam("2026-13-45")).toBeUndefined(); // QA-02: well-formed but not a calendar day
    expect(dayParam("2026-02-30")).toBeUndefined();
    expect(dayParam("2024-02-29")).toBe("2024-02-29");
    expect(activityUrl("2026-10-06", "u1")).toBe("/api/v1/telecaller/activity?date=2026-10-06&user_id=u1");
    expect(activityUrl()).toBe("/api/v1/telecaller/activity");
    expect(activityError({ status: 422, message: "future" })).toBe("future");
    expect(activityError(new Error("boom"))).toBe("Daily activity is unavailable right now.");
  });
});
