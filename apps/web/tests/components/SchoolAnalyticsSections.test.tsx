import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import SchoolGradePerformance from "@/components/SchoolGradePerformance";
import SchoolScorecardGrid from "@/components/SchoolScorecardGrid";
import SchoolStudentDevelopment from "@/components/SchoolStudentDevelopment";
import StudentScorecard, { ScorecardStateBadge } from "@/components/StudentScorecard";
import type { Scorecard, StudentDevelopment } from "@/lib/types";

afterEach(cleanup);

const card: Scorecard = {
  school_student_id: "s1",
  full_name: "Asha",
  grade: "10",
  portfolio_completion_pct: 40,
  areas: [
    { key: "psychometric", label: "Psychometric", state: "completed" },
    { key: "visa", label: "Visa", state: "not_in_plan" },
    { key: "internship", label: "Internship", state: "not_tracked" },
  ],
};
const development: StudentDevelopment = {
  headcounts: { students: 3, teachers: 1, parents: 2 },
  activities: [{ key: "career_guidance", label: "Career Guidance", completed: 1, pending: 2 }],
  by_grade: [],
  by_subject: [],
  by_term: [],
  at_risk: { items: [{ school_student_id: "s2", full_name: "Ben", grade: "9", average_pct: 32.5, result_count: 2 }], total: 1 },
  top_performers: { items: [], total: 0 },
  at_risk_below: 40,
  top_from: 85,
};

describe("ENH-016 report sections", () => {
  it("grade comparison: a captioned table with a column per grade and visible proxy definitions", () => {
    render(
      <SchoolGradePerformance
        data={{
          grades: ["9", "10"],
          students: { "9": 2, "10": 1 },
          metrics: [{ key: "career_readiness", label: "Career readiness", is_proxy: true, definition: "Guidance and psychometric done", cells: { "9": { count: 1, pct: 50 }, "10": { count: 0, pct: 0 } } }],
        }}
      />,
    );
    const table = screen.getByRole("table", { name: "Grade-wise comparison" });
    expect(within(table).getByRole("columnheader", { name: "Grade 10" })).toBeInTheDocument();
    expect(within(table).getByText("1 (50%)")).toBeInTheDocument();
    expect(screen.getByText("Estimate: Guidance and psychometric done")).toBeInTheDocument();
  });

  it("grade comparison: empty roster", () => {
    render(<SchoolGradePerformance data={{ grades: [], students: {}, metrics: [] }} />);
    expect(screen.getByText("No students on the roster yet.")).toBeInTheDocument();
  });

  it("student development: completed/pending table, labelled threshold form, at-risk list", () => {
    render(<SchoolStudentDevelopment data={development} basePath="/school/coordinator/reports" />);
    const table = screen.getByRole("table", { name: "Student development" });
    expect(within(table).getByRole("rowheader", { name: "Career Guidance" })).toBeInTheDocument();
    expect(within(table).getByText("2")).toBeInTheDocument();
    expect(screen.getByLabelText("At risk below (%)")).toHaveValue(40);
    expect(screen.getByLabelText("Top performer from (%)")).toHaveValue(85);
    expect(screen.getByRole("list", { name: "At-risk students" })).toHaveTextContent("Ben");
    expect(screen.getByText("No students at or above 85% yet.")).toBeInTheDocument();
    expect(screen.getByText("No published results yet.")).toBeInTheDocument();
  });

  it("student development: explains a rejected threshold pair next to the form, keeping the form usable", () => {
    render(<SchoolStudentDevelopment data={development} basePath="/r" thresholdError />);
    expect(screen.getByRole("alert")).toHaveTextContent("At-risk must be below the top-performer threshold. Showing the defaults.");
    expect(screen.getByLabelText("At risk below (%)")).toBeInTheDocument();
  });

  it("state badge always pairs an icon with words", () => {
    render(<ScorecardStateBadge state="in_progress" />);
    expect(screen.getByText("In progress")).toBeInTheDocument();
  });

  it("student scorecard lists every area and the portfolio percentage", () => {
    render(<StudentScorecard card={card} />);
    expect(screen.getByRole("heading", { name: "Progress scorecard" })).toBeInTheDocument();
    expect(screen.getByText("Completed")).toBeInTheDocument();
    expect(screen.getByText("Not in plan")).toBeInTheDocument();
    expect(screen.getByText("Not tracked yet")).toBeInTheDocument();
    expect(screen.getByText("Portfolio 40% complete")).toBeInTheDocument();
  });

  it("scorecard grid: grade filter form, student links, and paging links that keep the filter", () => {
    render(<SchoolScorecardGrid page={{ items: [card], total: 30, limit: 25, offset: 0 }} grade="10" basePath="/school/coordinator/reports" studentHref={(id) => `/school/coordinator/students/${id}`} />);
    expect(screen.getByLabelText("Grade")).toHaveValue("10");
    expect(screen.getByRole("link", { name: "Asha" })).toHaveAttribute("href", "/school/coordinator/students/s1");
    expect(screen.getByRole("link", { name: "Next page" })).toHaveAttribute("href", "/school/coordinator/reports?grade=10&offset=25#scorecards");
    expect(screen.queryByRole("link", { name: "Previous page" })).not.toBeInTheDocument();
    expect(screen.getByText("1–1 of 30")).toBeInTheDocument(); // the range counts the rows actually shown, not the page size
  });

  it("scorecard grid: offset past the end shows the empty message and a way back (Review Focus 4)", () => {
    render(<SchoolScorecardGrid page={{ items: [], total: 3, limit: 25, offset: 50 }} grade="" basePath="/r" studentHref={(id) => id} />);
    expect(screen.getByText("No students match this grade.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Previous page" })).toHaveAttribute("href", "/r?offset=25#scorecards");
  });
});
