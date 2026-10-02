import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import BdmProfileCard from "@/components/BdmProfileCard";
import BdmTeamTable from "@/components/BdmTeamTable";

const row = (id: string, active: boolean) => ({
  id, full_name: `BDM ${id}`, email: "", phone: "+91 1", active, bdm_type: "school" as const, employee_id: `E-${id}`, designation: null, department: null, territory: "Kochi",
});

afterEach(cleanup);

describe("BdmTeamTable (bdm-001)", () => {
  it("renders a labelled, focusable region with status in words", () => {
    render(<BdmTeamTable page={{ items: [row("a", true), row("b", false)], total: 2, limit: 50, offset: 0 }} />);
    const region = screen.getByRole("region", { name: "Team" });
    expect(region).toHaveAttribute("tabindex", "0");
    expect(within(region).getByText("Inactive")).toBeInTheDocument();
    expect(within(region).getAllByText("School", { selector: "td" })).toHaveLength(2);
    expect(screen.queryByRole("navigation", { name: "Team pages" })).toBeNull();
  });

  it("pages with links that keep the offset in the URL", () => {
    render(<BdmTeamTable page={{ items: [row("a", true)], total: 51, limit: 50, offset: 50 }} />);
    const pager = screen.getByRole("navigation", { name: "Team pages" });
    expect(within(pager).getByText("Showing 51–51 of 51")).toBeInTheDocument();
    expect(within(pager).getByRole("link", { name: "Previous page" })).toHaveAttribute("href", "/bdm/manager/team?offset=0");
    expect(within(pager).queryByRole("link", { name: "Next page" })).toBeNull();
  });

  it("offers Next (and no Previous) on the first page", () => {
    render(<BdmTeamTable page={{ items: Array.from({ length: 50 }, (_, i) => row(String(i), true)), total: 51, limit: 50, offset: 0 }} />);
    const pager = screen.getByRole("navigation", { name: "Team pages" });
    expect(within(pager).getByRole("link", { name: "Next page" })).toHaveAttribute("href", "/bdm/manager/team?offset=50");
    expect(within(pager).queryByRole("link", { name: "Previous page" })).toBeNull();
  });
});

describe("BdmProfileCard (bdm-001)", () => {
  it("shows every §1 field as label/value pairs, with dashes for blanks", () => {
    render(<BdmProfileCard me={{ id: "b", full_name: "Asha", email: "a@x.local", phone: null, active: false, division: "it",
      bdm_profile: { bdm_type: "college", employee_id: "E-1", designation: null, department: "Sales", territory: null, reporting_manager: { id: "m", full_name: "Meera", active: false } } }} />);
    const terms = screen.getAllByRole("term").map((t) => t.textContent);
    expect(terms).toEqual(["Name", "Employee ID", "Module", "Designation", "Department", "Territory", "Mobile", "Email", "Reporting manager", "Status"]);
    expect(screen.getByText("Meera (inactive)")).toBeInTheDocument();
    expect(screen.getByText("Inactive")).toBeInTheDocument();
  });
});
