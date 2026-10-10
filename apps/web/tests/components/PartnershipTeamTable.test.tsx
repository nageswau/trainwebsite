import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import PartnershipTeamTable from "@/components/PartnershipTeamTable";
import PartnershipMenuCard from "@/components/PartnershipMenuCard";

afterEach(cleanup);

const member = { id: "p1", full_name: "Rahul", email: "rahul@x.local", phone: null, active: false, employee_id: "P-1" };

describe("PartnershipTeamTable (upc-001 AC4)", () => {
  it("lists the head's managers with status words and a caption", () => {
    render(<PartnershipTeamTable page={{ items: [member], total: 1, limit: 50, offset: 0 }} />);
    expect(screen.getByRole("table", { name: "Partnership managers who report to you" })).toBeInTheDocument();
    expect(screen.getByText("Inactive")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.queryByRole("navigation")).toBeNull();
  });

  it("pages with links that keep the offset in the URL", () => {
    render(<PartnershipTeamTable page={{ items: [member], total: 120, limit: 50, offset: 50 }} />);
    expect(screen.getByRole("link", { name: "Previous page" })).toHaveAttribute("href", "/partnership/head/team?offset=0");
    expect(screen.getByRole("link", { name: "Next page" })).toHaveAttribute("href", "/partnership/head/team?offset=51");
  });
});

describe("PartnershipMenuCard (upc-001 PU8)", () => {
  it("lists the 3 areas still to come (16 of the 19 are live, incl. upc-025 Global Partnership Map, upc-009 Meetings, upc-011 Calendar, upc-018 Student Opportunities + University Performance, upc-016 Commercial Terms, upc-021 Targets & Forecast and upc-024 Global University Database), as text with no links", () => {
    render(<PartnershipMenuCard />);
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(items.some((i) => i.textContent?.includes("Global Partnership Map"))).toBe(false);
    expect(items.some((i) => i.textContent?.includes("Calendar"))).toBe(false);
    expect(items.some((i) => i.textContent?.includes("University Performance"))).toBe(false);
    expect(items.some((i) => i.textContent?.includes("Targets & Forecast"))).toBe(false);
    expect(items.some((i) => i.textContent?.includes("University Master"))).toBe(false);
    expect(items.some((i) => i.textContent?.includes("Global University Database"))).toBe(false);
    expect(items[0]).toHaveTextContent("Contact Management");
    expect(screen.queryByRole("link")).toBeNull();
  });
});
