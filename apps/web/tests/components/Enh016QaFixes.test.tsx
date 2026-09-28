import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CrossSchoolAnalytics from "@/components/CrossSchoolAnalytics";
import SchoolGradePerformance from "@/components/SchoolGradePerformance";
import SchoolScorecardGrid from "@/components/SchoolScorecardGrid";
import SchoolStudentDevelopment from "@/components/SchoolStudentDevelopment";
import ScrollToHash from "@/components/ScrollToHash";
import StudentScorecard from "@/components/StudentScorecard";
import type { CrossSchoolSummary, Scorecard, StudentDevelopment } from "@/lib/types";

// ENH-016 browser QA (2026-09-28), findings QA-016-01, 02, 05, 06, 07, 09, 10, 11, 12.
afterEach(cleanup);

const card: Scorecard = { school_student_id: "s1", full_name: "Asha", grade: "10", portfolio_completion_pct: 40, areas: [{ key: "visa", label: "Visa", state: "not_in_plan" }] };
const development = (over: Partial<StudentDevelopment> = {}): StudentDevelopment => ({
  headcounts: { students: 3, teachers: 1, parents: 1 },
  activities: [{ key: "career_guidance", label: "Career Guidance", completed: 1, pending: 2 }],
  by_grade: [{ key: "9", label: "9", average_pct: 50, count: 1 }],
  by_subject: [{ key: "Maths", label: "Maths", average_pct: 50, count: 1 }],
  by_term: [],
  at_risk: { items: [{ school_student_id: "s2", full_name: "Ben", grade: "9", average_pct: 32.5, result_count: 1 }], total: 1 },
  top_performers: { items: [], total: 0 },
  at_risk_below: 40,
  top_from: 85,
  ...over,
});
const summary: CrossSchoolSummary = {
  schools: { total: 3, active: 3, new: 0, renewal_due: 0 },
  students: { total: 1, by_grade: {}, career_guidance: 0, psychometric: 0, counselling: 0, global_education: 0 },
  services: { services_included: 0, delivered: 0, pending: 0, not_tracked: 0, utilization_pct: null },
  outcomes: {},
};

describe("QA-016-01 captions are screen-reader only", () => {
  it("uses the app's visually-hidden class on every ENH-016 caption that duplicates a heading", () => {
    render(
      <>
        <SchoolGradePerformance data={{ grades: ["9"], students: { "9": 1 }, metrics: [] }} />
        <SchoolStudentDevelopment data={development()} basePath="/r" />
        <SchoolScorecardGrid page={{ items: [card], total: 1, limit: 25, offset: 0 }} grade="" basePath="/r" studentHref={(id) => id} />
        <StudentScorecard card={card} />
        <CrossSchoolAnalytics summary={summary} page={{ items: [], total: 0, limit: 25, offset: 0 }} basePath="/a" />
      </>,
    );
    for (const name of ["Grade-wise comparison", "Student development", "Progress scorecards, 1 student", "Progress by area for Asha"]) {
      const caption = screen.getByText(name, { selector: "caption" });
      expect(caption).toHaveClass("visually-hidden");
    }
  });
});

describe("QA-016-02 the page lands on the section the form targeted", () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="scorecards"></div>';
    window.location.hash = "#scorecards";
  });
  afterEach(() => {
    window.location.hash = "";
  });
  it("scrolls the hash target into view once mounted", () => {
    const target = document.getElementById("scorecards")!;
    const spy = vi.fn();
    target.scrollIntoView = spy;
    render(<ScrollToHash />);
    expect(spy).toHaveBeenCalled();
  });
});

describe("QA-016-05 threshold messages", () => {
  it("shows whatever reason the loader gives", () => {
    render(<SchoolStudentDevelopment data={development()} basePath="/r" thresholdError="Thresholds must be between 0 and 100. Showing the defaults." />);
    expect(screen.getByRole("alert")).toHaveTextContent("Thresholds must be between 0 and 100. Showing the defaults.");
  });
});

describe("QA-016-06 scorecard grid empty and past-the-end states", () => {
  it("an empty school says so, not 'no match'", () => {
    render(<SchoolScorecardGrid page={{ items: [], total: 0, limit: 25, offset: 0 }} grade="" basePath="/r" studentHref={(id) => id} />);
    expect(screen.getByText("No students on the roster yet.")).toBeInTheDocument();
    expect(screen.queryByText("No students match this grade.")).not.toBeInTheDocument();
  });
  it("a grade with no students says no match", () => {
    render(<SchoolScorecardGrid page={{ items: [], total: 0, limit: 25, offset: 0 }} grade="8" basePath="/r" studentHref={(id) => id} />);
    expect(screen.getByText("No students match this grade.")).toBeInTheDocument();
  });
  it("past the end: says so and Previous goes to the real last page", () => {
    render(<SchoolScorecardGrid page={{ items: [], total: 30, limit: 25, offset: 9975 }} grade="" basePath="/r" studentHref={(id) => id} />);
    expect(screen.getByText("This page is past the end of the list.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Previous page" })).toHaveAttribute("href", "/r?offset=25#scorecards");
  });
});

describe("QA-016-07 / 09 admin table: search, empty and past-the-end states", () => {
  const row = { school_id: "a", name: "Alpha", tier: "gold", tier_valid_until: null, is_active: true, is_new: false, renewal_due: false, students: 1, student_participation: 0, pending_activities: 0, services_included: 0, delivered: 0, pending: 0, not_tracked: 0, utilization_pct: null };
  it("has a labelled search that keeps its value and carries it into paging links", () => {
    render(<CrossSchoolAnalytics summary={summary} page={{ items: [row], total: 60, limit: 25, offset: 25 }} basePath="/a" q="alp" />);
    expect(screen.getByLabelText("Search schools")).toHaveValue("alp");
    expect(screen.getByRole("link", { name: "Next page" })).toHaveAttribute("href", "/a?q=alp&offset=50");
    expect(screen.getByRole("link", { name: "Previous page" })).toHaveAttribute("href", "/a?q=alp");
  });
  it("a search with no match says so", () => {
    render(<CrossSchoolAnalytics summary={summary} page={{ items: [], total: 0, limit: 25, offset: 0 }} basePath="/a" q="zzz" />);
    expect(screen.getByText("No schools match “zzz”.")).toBeInTheDocument();
  });
  it("past the end: says so, no impossible range, Previous goes to the last page", () => {
    render(<CrossSchoolAnalytics summary={summary} page={{ items: [], total: 5, limit: 25, offset: 1000 }} basePath="/a" />);
    expect(screen.getByText("This page is past the end of the list.")).toBeInTheDocument();
    expect(screen.queryByText(/1001–1000/)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Previous page" })).toHaveAttribute("href", "/a");
  });
});

describe("QA-016-10 / 11 heading level and plurals", () => {
  it("the scorecard card heading matches its sibling cards (h3)", () => {
    render(<StudentScorecard card={card} />);
    expect(screen.getByRole("heading", { level: 3, name: "Progress scorecard" })).toBeInTheDocument();
  });
  it("uses singular words for one", () => {
    render(<SchoolStudentDevelopment data={development()} basePath="/r" />);
    expect(screen.getByText("3 students · 1 teacher · 1 parent")).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "At-risk students" })).getByText(/\(1 result\)/)).toBeInTheDocument();
  });
});

describe("QA-016-12 the two report forms keep each other's settings", () => {
  it("the thresholds form carries the grade filter", () => {
    const { container } = render(<SchoolStudentDevelopment data={development({ at_risk_below: 30, top_from: 90 })} basePath="/r" grade="10" />);
    expect(container.querySelector('input[type="hidden"][name="grade"]')).toHaveValue("10");
  });
  it("the grade form and paging links carry the thresholds", () => {
    const { container } = render(
      <SchoolScorecardGrid page={{ items: [card], total: 30, limit: 25, offset: 0 }} grade="" basePath="/r" studentHref={(id) => id} thresholds={{ at_risk_below: "30", top_from: "90" }} />,
    );
    expect(container.querySelector('input[type="hidden"][name="at_risk_below"]')).toHaveValue("30");
    expect(container.querySelector('input[type="hidden"][name="top_from"]')).toHaveValue("90");
    expect(screen.getByRole("link", { name: "Next page" })).toHaveAttribute("href", "/r?at_risk_below=30&top_from=90&offset=25#scorecards");
  });
});
