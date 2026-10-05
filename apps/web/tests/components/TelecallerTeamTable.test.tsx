import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import TelecallerTeamTable from "@/components/TelecallerTeamTable";
import type { TelecallerTeamRow } from "@/lib/telecaller";

afterEach(cleanup);

const row = (i: number, active = true): TelecallerTeamRow => ({
  id: `t${i}`, full_name: `Caller ${i}`, email: `c${i}@x.local`, phone: i % 2 ? null : "+91 1", active, team: i % 2 ? "overseas" : "it", employee_id: `E-${i}`,
});

describe("TelecallerTeamTable (tel-001 AC4)", () => {
  it("lists each report with team and a worded status", () => {
    render(<TelecallerTeamTable page={{ items: [row(1), row(2, false)], total: 2, limit: 50, offset: 0 }} />);
    const table = within(screen.getByRole("region", { name: "Team" }));
    expect(table.getByText("Caller 1")).toBeInTheDocument();
    expect(table.getByText("Overseas")).toBeInTheDocument();
    expect(table.getByText("Inactive")).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Team pages" })).toBeNull();
  });

  it("pages with links that keep the offset in the URL", () => {
    render(<TelecallerTeamTable page={{ items: [row(51)], total: 120, limit: 50, offset: 50 }} />);
    const pager = within(screen.getByRole("navigation", { name: "Team pages" }));
    expect(pager.getByText("Showing 51–51 of 120")).toBeInTheDocument();
    expect(pager.getByRole("link", { name: "Previous page" })).toHaveAttribute("href", "/telecaller/manager/team?offset=0");
    expect(pager.getByRole("link", { name: "Next page" })).toHaveAttribute("href", "/telecaller/manager/team?offset=51");
  });
});
