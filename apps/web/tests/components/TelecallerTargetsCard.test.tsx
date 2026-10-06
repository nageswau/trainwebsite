import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import TelecallerTargetsCard from "@/components/TelecallerTargetsCard";

const row = (kpi: string, value: number | null, source: "user" | "team" | null = value === null ? null : "team") => ({ kpi, value, source });
const KPIS = ["calls", "connected_calls", "qualified_leads", "follow_ups", "counselling_appointments", "conversions"];
const mine = {
  date: "2026-10-06", month: "2026-10-01", team: "it" as const, user: { id: "u1", full_name: "Ravi" },
  daily: KPIS.map((k) => row(k, k === "calls" ? 90 : k === "qualified_leads" ? 15 : null, k === "calls" ? "user" : undefined)),
  monthly: KPIS.map((k) => row(k, k === "conversions" ? 60 : null)),
};

afterEach(cleanup);

describe("TelecallerTargetsCard (tel-022 G4)", () => {
  it("shows today's and this month's targets, with Not set for gaps", () => {
    render(<TelecallerTargetsCard targets={mine} />);
    const card = screen.getByRole("region", { name: "My targets" });
    expect(within(card).getByRole("columnheader", { name: /Today/ })).toBeInTheDocument();
    expect(within(card).getByRole("columnheader", { name: /October 2026/ })).toBeInTheDocument();
    const calls = within(card).getByText("Calls").closest("tr")!;
    expect(within(calls).getByText("90")).toBeInTheDocument();
    expect(within(within(card).getByText("Conversions").closest("tr")!).getByText("60")).toBeInTheDocument();
    expect(within(within(card).getByText("Follow-ups").closest("tr")!).getAllByText("Not set")).toHaveLength(2);
    expect(within(card).getByText(/Achieved figures will appear here/)).toBeInTheDocument();
  });

  it("says so when the targets could not be loaded", () => {
    render(<TelecallerTargetsCard targets={null} />);
    expect(screen.getByText("Targets are unavailable right now.")).toBeInTheDocument();
  });
});
