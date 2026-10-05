import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import SchoolKpiBoard from "@/components/SchoolKpiBoard";
import SectionUnavailable from "@/components/SectionUnavailable";

afterEach(cleanup);

const kpi = (key: string, label: string, value: number | null, tracked = true, note: string | null = null) => ({ key, label, value, tracked, note });

describe("SchoolKpiBoard", () => {
  it("groups KPIs under h3 headings and formats numbers", () => {
    render(<SchoolKpiBoard kpis={[kpi("total_students", "Total Students", 1250), kpi("psychometric_tests_completed", "Psychometric Tests Completed", 720)]} />);
    expect(screen.getByRole("heading", { level: 2, name: "School at a glance" })).toBeInTheDocument();
    const students = screen.getByRole("region", { name: "Students" });
    expect(within(students).getByRole("heading", { level: 3, name: "Students" })).toBeInTheDocument();
    expect(within(students).getByText("1,250")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Career & assessment" })).toHaveTextContent("720");
  });

  it("shows an untracked KPI as 'Not tracked yet' with its note, never 0", () => {
    render(<SchoolKpiBoard kpis={[kpi("internships", "Internships", null, false, "No confirmed School internship model exists yet.")]} />);
    expect(screen.getByText("Not tracked yet")).toBeInTheDocument();
    expect(screen.getByText("No confirmed School internship model exists yet.")).toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("renders an honest empty state", () => {
    render(<SchoolKpiBoard kpis={[]} />);
    expect(screen.getByText("No figures to show yet.")).toBeInTheDocument();
  });
});

describe("SectionUnavailable", () => {
  it("announces the failure politely and keeps its heading", () => {
    render(<SectionUnavailable title="Grade-wise comparison" />);
    expect(screen.getByRole("heading", { name: "Grade-wise comparison" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("This section couldn't load. Refresh to try again.");
  });
});
