import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import CrossSchoolAnalytics from "@/components/CrossSchoolAnalytics";
import { PORTAL_NAV, SUPER_ADMIN_NAV } from "@/lib/navigation";
import type { CrossSchoolSummary, SchoolUtilizationRow } from "@/lib/types";

afterEach(cleanup);

const summary: CrossSchoolSummary = {
  schools: { total: 4, active: 3, new: 1, renewal_due: 2 },
  students: { total: 1200, by_grade: { "9": 600, "10": 600 }, career_guidance: 40, psychometric: 30, counselling: 20, global_education: 10 },
  services: { services_included: 30, delivered: 12, pending: 8, not_tracked: 10, utilization_pct: 60 },
  outcomes: { applications: { value: 9, tracked: true, note: null }, scholarships: { value: null, tracked: false, note: "No link yet." } },
};
const row: SchoolUtilizationRow = {
  school_id: "a", name: "Alpha School", tier: "gold", tier_valid_until: "2026-10-01", status: "active", is_new: false, renewal_due: true,
  students: 50, student_participation: 20, pending_activities: 2, services_included: 12, delivered: 6, pending: 3, not_tracked: 3, utilization_pct: 66.7,
};

describe("CrossSchoolAnalytics", () => {
  it("shows the four KPI groups, untracked outcomes in words, and the school table", () => {
    render(<CrossSchoolAnalytics summary={summary} page={{ items: [row], total: 1, limit: 25, offset: 0 }} basePath="/overseas/admin/school-analytics" />);
    for (const name of ["Schools", "Students", "Services", "Outcomes"]) expect(screen.getByRole("region", { name })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Students" })).toHaveTextContent("1,200");
    expect(screen.getByRole("region", { name: "Outcomes" })).toHaveTextContent("Not tracked yet");
    const table = screen.getByRole("table", { name: "Service utilization by school" });
    expect(within(table).getByRole("rowheader", { name: "Alpha School" })).toBeInTheDocument();
    expect(within(table).getByText("66.7%")).toBeInTheDocument();
    expect(within(table).getByText("Renewal due")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Next page" })).not.toBeInTheDocument();
  });

  it("pages through schools", () => {
    render(<CrossSchoolAnalytics summary={summary} page={{ items: [row], total: 60, limit: 25, offset: 25 }} basePath="/x" />);
    expect(screen.getByRole("link", { name: "Previous page" })).toHaveAttribute("href", "/x");
    expect(screen.getByRole("link", { name: "Next page" })).toHaveAttribute("href", "/x?offset=50");
  });

  it("empty and failed sections", () => {
    render(<CrossSchoolAnalytics summary={null} page={{ items: [], total: 0, limit: 25, offset: 0 }} basePath="/x" />);
    expect(screen.getByRole("status")).toHaveTextContent("This section couldn't load.");
    expect(screen.getByText("No partner schools yet.")).toBeInTheDocument();
  });
});

describe("navigation", () => {
  it("links School Analytics for overseas and super admins", () => {
    expect(PORTAL_NAV["overseas/admin"].some((i) => i.href === "/overseas/admin/school-analytics")).toBe(true);
    expect(SUPER_ADMIN_NAV.some((i) => i.href === "/overseas/admin/school-analytics" && i.label === "School Analytics")).toBe(true);
  });
});
