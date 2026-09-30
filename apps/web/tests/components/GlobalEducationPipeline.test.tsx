import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import GlobalEducationFunnel from "@/components/GlobalEducationFunnel";
import GlobalEducationStudentTable from "@/components/GlobalEducationStudentTable";
import type { GlobalEducationPipeline } from "@/lib/types";

const row = (n: number) => ({ school_student_id: `id-${n}`, full_name: `Student ${n}`, student_code: `C0DE000${n}`, grade: "12", furthest_stage: "offer", furthest_stage_label: "Offer received", visa_stage_label: n === 1 ? "Documentation" : null, application_count: 2 });
const data = (over: Partial<GlobalEducationPipeline> = {}): GlobalEducationPipeline => ({
  grade: 12, students_in_scope: 150, bridged_students: 80,
  funnel: [{ key: "pathway", label: "Global education pathway", count: 80 }, { key: "offer", label: "Offer received", count: 18 }],
  not_tracked: [{ key: "scholarship", label: "Scholarships", note: "No school-student scholarship link exists yet." }],
  students: { items: [row(1), row(2)], total: 80, limit: 25, offset: 0 },
  ...over,
});

afterEach(cleanup);

describe("GlobalEducationFunnel", () => {
  it("states the scope, the §19 boundary and every stage count as text", () => {
    render(<GlobalEducationFunnel data={data()} />);
    expect(screen.getByText("150 students in Grade 12 · 80 students on the global education pathway")).toBeTruthy();
    expect(screen.getByText("High-level stage only. Application details are handled by EduSphere's application team.")).toBeTruthy();
    const funnel = screen.getByRole("list", { name: "Global education funnel" });
    expect(within(funnel).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["Global education pathway80", "Offer received18"]);
  });

  it("shows untracked stages as not tracked, never as zero", () => {
    render(<GlobalEducationFunnel data={data()} />);
    const group = screen.getByRole("region", { name: "Not tracked yet" });
    expect(within(group).getByText("Scholarships")).toBeTruthy();
    expect(within(group).getByText("No school-student scholarship link exists yet.")).toBeTruthy();
  });

  it("drops the grade from the scope line when no grade is chosen", () => {
    render(<GlobalEducationFunnel data={data({ grade: null })} />);
    expect(screen.getByText("150 students · 80 students on the global education pathway")).toBeTruthy();
  });
});

describe("GlobalEducationStudentTable", () => {
  const base = "/school/coordinator/global-education";

  it("renders a captioned table with row headers and the high-level columns only", () => {
    render(<GlobalEducationStudentTable page={data().students} grade="12" basePath={base} />);
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Student", "Student ID", "Grade", "Furthest stage", "Visa", "Applications"]);
    expect(within(table).getByRole("rowheader", { name: "Student 1" })).toBeTruthy();
    expect(within(table).getByText("Documentation")).toBeTruthy();
    expect(within(table).getAllByText("—")).toHaveLength(1); // no visa case
    expect(within(table).getByText(/Global education students, 80 students/)).toBeTruthy();
  });

  it("has a labelled grade select inside a GET form that keeps the page URL", () => {
    render(<GlobalEducationStudentTable page={data().students} grade="12" basePath={base} />);
    const select = screen.getByLabelText("Grade") as HTMLSelectElement;
    expect(select.value).toBe("12");
    expect(select.closest("form")?.getAttribute("method")).toBe("get");
    expect(select.closest("form")?.getAttribute("action")).toBe(`${base}#students`);
  });

  it("pages forward with the grade kept", () => {
    render(<GlobalEducationStudentTable page={data().students} grade="12" basePath={base} />);
    expect(screen.getByRole("link", { name: "Next page" }).getAttribute("href")).toBe(`${base}?grade=12&offset=25#students`);
    expect(screen.queryByRole("link", { name: "Previous page" })).toBeNull();
  });

  it("empty school, empty grade and past-end each say so", () => {
    const empty = { items: [], total: 0, limit: 25, offset: 0 };
    const { rerender } = render(<GlobalEducationStudentTable page={empty} grade="" basePath={base} />);
    expect(screen.getByText("No students from this school are on the global education pathway yet. Students appear here once an EduSphere counselor links their application.")).toBeTruthy();
    rerender(<GlobalEducationStudentTable page={empty} grade="11" basePath={base} />);
    expect(screen.getByText("No students in this grade are on the global education pathway.")).toBeTruthy();
    rerender(<GlobalEducationStudentTable page={{ items: [], total: 30, limit: 25, offset: 100 }} grade="" basePath={base} />);
    expect(screen.getByText("This page is past the end of the list.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Previous page" }).getAttribute("href")).toBe(`${base}?offset=25#students`);
  });
});

// QA17-01: the route's loading.tsx streams the page, so `#students` is still hidden when the browser performs the fragment
// scroll after "Next →" / "Show" and the page stays at the top. The card scrolls itself into view once it is on screen.
describe("GlobalEducationStudentTable #students landing (QA17-01)", () => {
  const base = "/school/coordinator/global-education";
  afterEach(() => {
    window.history.replaceState(null, "", "/");
    vi.restoreAllMocks();
  });

  it("scrolls the student card into view when the URL targets #students", () => {
    window.history.replaceState(null, "", `${base}?offset=25#students`);
    const scroll = vi.fn();
    Element.prototype.scrollIntoView = scroll;
    render(<GlobalEducationStudentTable page={data().students} grade="" basePath={base} />);
    expect(scroll).toHaveBeenCalledTimes(1);
    expect((scroll.mock.contexts[0] as HTMLElement).id).toBe("students");
  });

  it("leaves the scroll position alone when the URL does not target #students", () => {
    window.history.replaceState(null, "", base);
    const scroll = vi.fn();
    Element.prototype.scrollIntoView = scroll;
    render(<GlobalEducationStudentTable page={data().students} grade="" basePath={base} />);
    expect(scroll).not.toHaveBeenCalled();
  });
});

// Final verification (axe `scrollable-region-focusable`, WCAG 2.1.1): at phone width the table scrolls sideways and its names
// are plain text, so the scroll box itself must take keyboard focus for the hidden columns to be reachable.
describe("GlobalEducationStudentTable keyboard-scrollable table", () => {
  it("wraps the table in a labelled region that takes keyboard focus", () => {
    render(<GlobalEducationStudentTable page={data().students} grade="" basePath="/school/coordinator/global-education" />);
    const region = screen.getByRole("region", { name: "Global education students" });
    expect(region.tabIndex).toBe(0);
    expect(region.classList.contains("table-scroll")).toBe(true);
    expect(within(region).getByRole("table")).toBeTruthy();
  });
});
