import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import AdminTrainingTiles, { type TrainingTiles } from "@/components/AdminTrainingTiles";

afterEach(cleanup);

const COLUMNS = [
  { key: "course", label: "Course" }, { key: "batches", label: "Batches" }, { key: "enrolments", label: "Enrolments" },
  { key: "active", label: "Active" }, { key: "completed", label: "Completed" }, { key: "dropped", label: "Dropped" },
];
const BASE: TrainingTiles = {
  enrolments: 12, active: 7, completed: 4, dropped: 1, average_progress: 63.5, at_risk: 3, at_risk_threshold: 75,
  courses: { columns: COLUMNS, items: [{ course: "Python", batches: 2, enrolments: 12, active: 7, completed: 4, dropped: 1 }], total: 1 },
};

// nehn-011 (DEC-SCOPE-311): each tile is a link to the report it totals, in the portal's own report library.
describe("AdminTrainingTiles (nehn-011)", () => {
  it("links each tile to its report, the at-risk one pre-filtered at the threshold", () => {
    render(<AdminTrainingTiles training={BASE} basePath="/admin/report-library" />);
    const link = (name: RegExp) => screen.getByRole("link", { name });
    expect(link(/Enrolments\s*12/)).toHaveAttribute("href", "/admin/report-library?report=courses");
    expect(link(/Completed\s*4/)).toHaveAttribute("href", "/admin/report-library?report=completions");
    expect(link(/Average progress\s*63.5%/)).toHaveAttribute("href", "/admin/report-library?report=student-courses");
    expect(link(/At-risk students\s*3/)).toHaveAttribute("href", "/admin/report-library?report=attendance&attendance_below=75");
    expect(screen.getByText(/attendance below 75%/i)).toBeInTheDocument();
  });

  it("hides the fee tiles without the financial figures and shows them with", () => {
    const { rerender } = render(<AdminTrainingTiles training={BASE} basePath="/it/admin/report-library" />);
    expect(screen.queryByText("Course fees collected")).not.toBeInTheDocument();
    rerender(<AdminTrainingTiles training={{ ...BASE, fees_collected: 150000, fees_pending: 25000.5 }} basePath="/it/admin/report-library" />);
    expect(screen.getByRole("link", { name: /Course fees collected\s*₹1,50,000/ })).toHaveAttribute("href", "/it/admin/report-library?report=courses");
    expect(screen.getByRole("link", { name: /Course fees pending\s*₹25,000.5/ })).toBeInTheDocument();
  });

  it("shows the course-wise table with labelled cells and a link to the full report", () => {
    render(<AdminTrainingTiles training={BASE} basePath="/admin/report-library" />);
    const table = screen.getByRole("table", { name: /Course-wise/ });
    // QA-01: `compact` lifts the shared 650px min-width, so the stacked cells' values stay on a phone screen.
    expect(table.className.split(" ")).toEqual(expect.arrayContaining(["table", "compact", "stack"]));
    expect(within(table).getByRole("columnheader", { name: "Enrolments" })).toBeInTheDocument();
    expect(within(table).getByText("Python")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /View the course-wise report/ })).toHaveAttribute("href", "/admin/report-library?report=courses");
  });

  it("an empty system shows zeros, a dash for the average and an empty-table message", () => {
    const empty: TrainingTiles = { ...BASE, enrolments: 0, active: 0, completed: 0, dropped: 0, average_progress: null, at_risk: 0, courses: { columns: COLUMNS, items: [], total: 0 } };
    render(<AdminTrainingTiles training={empty} basePath="/admin/report-library" />);
    expect(screen.getByRole("link", { name: /Enrolments\s*0/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Average progress\s*—/ })).toBeInTheDocument();
    expect(screen.getByText("No courses with batches yet.")).toBeInTheDocument();
  });

  it("renders nothing without a training block", () => {
    const { container } = render(<AdminTrainingTiles training={undefined} basePath="/admin/report-library" />);
    expect(container).toBeEmptyDOMElement();
  });
});
