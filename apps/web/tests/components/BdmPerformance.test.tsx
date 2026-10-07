import { describe, expect, it } from "vitest";

import BdmHierarchy from "@/components/BdmHierarchy";
import BdmPerformanceFigures from "@/components/BdmPerformanceFigures";
import BdmPerformanceTable from "@/components/BdmPerformanceTable";
import type { Figures, Hierarchy, Performance } from "@/lib/bdmPerformance";
import { elements, text } from "@/tests/helpers/elementTree";

// bdm-024 (DEC-SCOPE-111): the three views are plain functions of their data, so they are called directly.
const TYPES = ["agent", "school", "college"] as const;
const row = (key: string, label: string, values: (number | string | null)[], definition = `${label} definition.`) => ({
  key, label, cells: TYPES.map((type, i) => ({ type, tracked: values[i] !== null, value: values[i], definition })),
});
const performance: Performance = {
  from: "2026-10-01", to: "2026-10-31", manager: null, type: null, bdms: [],
  rows: [row("P-01", "BDMs", [3, 2, 3]), row("P-02", "Meetings", [80, 65, 75]), row("P-08", "Revenue", [null, null, "12500.00"])],
};
const F = { from: "2026-10-01", to: "2026-10-31" };
const allText = (t: ReturnType<typeof elements>) => t.map((el) => text(el)).join(" ");
const links = (t: ReturnType<typeof elements>) => t.filter((el) => typeof el.props.href === "string");

describe("bdm-024 performance table (L1)", () => {
  const tree = elements(BdmPerformanceTable({ data: performance, filters: F }));

  it("is a captioned table of KPIs x BDM types", () => {
    const table = tree.find((el) => el.type === "table")!;
    expect(table).toBeTruthy();
    expect(text(tree.find((el) => el.type === "caption")!)).toContain("1 Oct 2026 – 31 Oct 2026");
    expect(tree.filter((el) => el.type === "th" && el.props.scope === "col").map((el) => text(el))).toEqual(["KPI", "Agent BDM", "School BDM", "College BDM"]);
    expect(tree.filter((el) => el.type === "th" && el.props.scope === "row").map((el) => text(el))).toEqual(["BDMs", "Meetings", "Revenue"]);
  });

  it("writes each figure's definition below the table, per type where they differ", () => {
    expect(allText(tree)).toContain("Meetings: Meetings definition.");
    const perType = elements(BdmPerformanceTable({ data: { ...performance, rows: [{ key: "P-07", label: "Students", cells: [
      { type: "agent", tracked: true, value: 1, definition: "A." }, { type: "school", tracked: true, value: 2, definition: "S." },
      { type: "college", tracked: true, value: 3, definition: "C." }] }] }, filters: F }));
    expect(allText(perType)).toContain("Students — Agent BDM: A. School BDM: S. College BDM: C.");
  });

  it("links every tracked number to the BDMs of its type, keeping the period", () => {
    const meetings = links(tree).find((el) => el.props["aria-label"] === "Agent BDM Meetings: 80. View the BDMs")!;
    expect(meetings.props.href).toBe("/bdm/manager/performance/agent?from=2026-10-01&to=2026-10-31");
    expect(text(meetings)).toBe("80");
    expect(links(tree).find((el) => text(el) === "₹12,500.00")!.props.href).toBe("/bdm/manager/performance/college?from=2026-10-01&to=2026-10-31");
  });

  it("labels untracked figures in words and does not link them", () => {
    expect(allText(tree).match(/Not tracked/g)!.length).toBeGreaterThanOrEqual(2);
    expect(links(tree).some((el) => text(el) === "Not tracked")).toBe(false);
  });

  it("scrolls inside its container on a phone", () => {
    expect(tree.some((el) => el.type === "div" && String(el.props.className).includes("table-scroll"))).toBe(true);
  });
});

const figures = (over: Partial<Figures> = {}): Figures => ({
  meetings: 1, trips: 2, new_organizations: 0, mous: 1, leads: 4, students: 3, revenue: "100.00", ...over,
});

describe("bdm-024 figures table (L2 / L3)", () => {
  const tree = elements(BdmPerformanceFigures({
    caption: "College BDMs", first: "BDM",
    rows: [
      { key: "b1", name: "Asha", href: "/bdm/manager/performance/bdms/b1", note: undefined, figures: figures() },
      { key: "b2", name: "Ravi", href: "/bdm/manager/performance/bdms/b2", note: "Inactive", figures: figures({ trips: null, revenue: null }) },
    ],
    total: figures({ meetings: 2, trips: 2, mous: 2, leads: 8, students: 6, revenue: "100.00" }),
    empty: "No BDMs of this type in the team.",
  }));

  it("names each row with a link to the next level and keeps a Total row", () => {
    expect(links(tree).find((el) => text(el) === "Asha")!.props.href).toBe("/bdm/manager/performance/bdms/b1");
    expect(allText(tree)).toContain("Inactive");
    expect(tree.some((el) => el.type === "tfoot")).toBe(true);
    expect(tree.filter((el) => el.type === "th" && el.props.scope === "col").map((el) => text(el))).toEqual(
      ["BDM", "Meetings", "Travel Trips", "New Organizations", "MoUs", "Leads", "Students", "Revenue"]);
  });

  it("links each figure to the row's next level; a figure that does not apply is a dash, not a link", () => {
    const leads = links(tree).find((el) => el.props["aria-label"] === "Asha Leads: 4")!;
    expect(leads.props.href).toBe("/bdm/manager/performance/bdms/b1");
    expect(allText(tree)).toContain("Not tracked");
    expect(links(tree).some((el) => text(el) === "—" || text(el) === "Not tracked")).toBe(false);
  });

  it("shows the empty message instead of an empty table", () => {
    const empty = elements(BdmPerformanceFigures({ caption: "x", first: "BDM", rows: [], total: figures(), empty: "No BDMs of this type in the team." }));
    expect(allText(empty)).toContain("No BDMs of this type in the team.");
    expect(empty.some((el) => el.type === "table")).toBe(false);
  });
});

const hierarchy: Hierarchy = {
  manager: null, as_of: "2026-10-07T05:00:00Z",
  types: [
    {
      type: "agent", label: "Agent BDM", bdm_count: 1, organization_count: 1, not_linked: 2, totals: [4, 7, 1, null],
      chain: [
        { key: "students", label: "Students", definition: "d", tracked: true }, { key: "applications", label: "Applications", definition: "d", tracked: true },
        { key: "enrollment", label: "Enrollment", definition: "d", tracked: true }, { key: "revenue", label: "Revenue", definition: "Not tracked: d", tracked: false },
      ],
      bdms: [
        { id: "b1", full_name: "Asha", active: true, organization_count: 1, not_linked: 2, totals: [4, 7, 1, null],
          organizations: [{ id: "o1", code: "ORG-1", name: "ABC Overseas", counts: [4, 7, 1, null] }] },
        { id: "b2", full_name: "Ravi", active: false, organization_count: 0, not_linked: 0, totals: [0, 0, 0, null], organizations: [] },
      ],
    },
    { type: "school", label: "School BDM", bdm_count: 0, organization_count: 0, not_linked: 0, totals: [0, null, 0, 0], chain: [], bdms: [] },
  ],
};

describe("bdm-024 master view", () => {
  const tree = elements(BdmHierarchy({ data: hierarchy }));

  it("is a hierarchy of type -> BDMs -> organizations with each type's value chain", () => {
    expect(tree.filter((el) => el.type === "h3").map((el) => text(el))).toEqual(["Agent BDM", "School BDM"]);
    expect(allText(tree)).toContain("Students → Applications → Enrollment → Revenue");
    expect(allText(tree)).toContain("2 not onboarded yet");
    expect(tree.filter((el) => el.type === "details").length).toBe(2);
    expect(links(tree).find((el) => text(el) === "ABC Overseas")!.props.href).toBe("/bdm/manager/organizations/o1");
  });

  it("marks inactive BDMs and empty branches in words", () => {
    expect(allText(tree)).toContain("Ravi (inactive)");
    expect(allText(tree)).toContain("No linked organizations yet.");
    expect(allText(tree)).toContain("No School BDMs in this team.");
    expect(allText(tree)).toContain("Not tracked");
  });
});
