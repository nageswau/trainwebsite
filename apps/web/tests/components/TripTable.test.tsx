import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import TripTable from "@/components/TripTable";

import { row } from "./tripFixtures";

afterEach(cleanup);

describe("TripTable (bdm-010)", () => {
  it("shows code, route, rupee costs and both statuses in words inside a focusable region", () => {
    const page = { items: [row({ actual_cost: "1650.50", approval_status: "submitted" })], total: 1, limit: 50, offset: 0 };
    render(<TripTable page={page} label="My trips" basePath="/bdm/travel" detailHref={(id) => `/bdm/travel/${id}`} />);
    const region = screen.getByRole("region", { name: "My trips" });
    expect(region).toHaveAttribute("tabindex", "0");
    expect(within(region).getByRole("link", { name: "TRV-000001" })).toHaveAttribute("href", "/bdm/travel/t1");
    expect(within(region).getByText("Hyderabad → Vijayawada")).toBeInTheDocument();
    expect(within(region).getByText("₹2,500.00")).toBeInTheDocument();
    expect(within(region).getByText("₹1,650.50")).toBeInTheDocument();
    expect(within(region).getByText("Approval: Submitted")).toBeInTheDocument();
    expect(within(region).getByText("Travel: Planned")).toBeInTheDocument();
    expect(within(region).queryByText("Asha")).toBeNull();
    expect(screen.queryByRole("navigation")).toBeNull();
  });

  it("shows the BDM column for managers and pages with links that keep the filter", () => {
    const page = { items: [row()], total: 51, limit: 50, offset: 0 };
    render(<TripTable page={page} label="Team trips" basePath="/bdm/manager/approvals" query="approval_status=submitted" showBdm
      detailHref={(id) => `/bdm/manager/trips/${id}`} />);
    expect(screen.getByText("Asha")).toBeInTheDocument();
    const pager = screen.getByRole("navigation", { name: "Team trips pages" });
    expect(within(pager).getByText("Showing 1–1 of 51")).toBeInTheDocument();
    expect(within(pager).getByRole("link", { name: "Next page" })).toHaveAttribute("href", "/bdm/manager/approvals?approval_status=submitted&offset=1");
    expect(within(pager).queryByRole("link", { name: "Previous page" })).toBeNull();
  });
});
