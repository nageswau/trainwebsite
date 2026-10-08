import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import RecruiterProfileCard from "@/components/RecruiterProfileCard";
import RecruiterTeamTable from "@/components/RecruiterTeamTable";
import type { RecruiterMe, RecruiterTeamRow } from "@/lib/recruiter";

afterEach(cleanup);

const row = (i: number, active = true, employee_id: string | null = `R-${i}`): RecruiterTeamRow => ({
  id: `r${i}`, full_name: `Recruiter ${i}`, email: `r${i}@x.local`, phone: i % 2 ? null : "+91 1", active, employee_id,
});

describe("RecruiterTeamTable (rec-001 AC4)", () => {
  it("lists each report with Employee ID, mobile and a worded status", () => {
    render(<RecruiterTeamTable page={{ items: [row(1), row(2, false, null)], total: 2, limit: 50, offset: 0 }} />);
    const table = within(screen.getByRole("region", { name: "Team" }));
    expect(table.getByText("Recruiter 1")).toBeInTheDocument();
    expect(table.getByText("R-1")).toBeInTheDocument();
    expect(table.getByText("Inactive")).toBeInTheDocument();
    expect(table.getAllByText("—").length).toBe(2); // the missing mobile and the missing Employee ID
    expect(screen.queryByRole("navigation", { name: "Team pages" })).toBeNull();
  });

  it("pages with links that keep the offset in the URL", () => {
    render(<RecruiterTeamTable page={{ items: [row(51)], total: 120, limit: 50, offset: 50 }} />);
    const pager = within(screen.getByRole("navigation", { name: "Team pages" }));
    expect(pager.getByText("Showing 51–51 of 120")).toBeInTheDocument();
    expect(pager.getByRole("link", { name: "Previous page" })).toHaveAttribute("href", "/recruiter/manager/team?offset=0");
    expect(pager.getByRole("link", { name: "Next page" })).toHaveAttribute("href", "/recruiter/manager/team?offset=51");
  });
});

describe("RecruiterProfileCard (rec-001 AC5)", () => {
  const me = (profile: RecruiterMe["recruiter_profile"]): RecruiterMe => ({
    id: "u", full_name: "Kiran", email: "k@x.local", phone: null, active: true, division: "it", recruiter_profile: profile,
  });

  it("shows the manager, or that none is set yet", () => {
    render(<RecruiterProfileCard me={me({ employee_id: "R-9", reporting_manager: { id: "m", full_name: "Nisha", active: false } })} />);
    expect(screen.getByText("Nisha (inactive)")).toBeInTheDocument();
    expect(screen.getByText("R-9")).toBeInTheDocument();
    cleanup();
    render(<RecruiterProfileCard me={me({ employee_id: null, reporting_manager: null })} />);
    expect(screen.getAllByText("Not set yet — contact your administrator")).toHaveLength(2); // Employee ID and manager
  });
});
