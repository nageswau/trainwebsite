import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import PsychometricResultDetails, { PsychometricResultsList } from "@/components/PsychometricResultDetails";

afterEach(cleanup);

const FULL = {
  test_date: "2026-09-10", strengths: ["Logical reasoning", "Verbal ability"], interest_areas: ["Design"], personality_indicators: null,
  recommended_careers: ["Software engineer"], recommended_stream: ["Science (PCM)"], counsellor_remarks: "Line one\nLine two",
  parent_discussion_on: "2026-09-15", parent_discussion_notes: "Agreed on a design camp.", follow_up_on: "2026-10-15",
};
const row = (name: string) => screen.getByText(name, { selector: "dt" }).closest(".record-details-row") as HTMLElement;

describe("PsychometricResultDetails", () => {
  it("shows every recorded field with its label and omits empty ones", () => {
    render(<PsychometricResultDetails result={FULL} />);
    expect(within(row("Strengths")).getByText("Logical reasoning, Verbal ability")).toBeTruthy();
    expect(within(row("Career recommendations")).getByText("Software engineer")).toBeTruthy();
    expect(within(row("Recommended streams")).getByText("Science (PCM)")).toBeTruthy();
    expect(row("Counsellor remarks").textContent).toContain("Line one\nLine two");
    expect(row("Parent discussion").textContent).toContain("Agreed on a design camp.");
    expect(row("Test date")).toBeTruthy();
    expect(row("Follow-up")).toBeTruthy();
    expect(screen.queryByText("Personality indicators")).toBeNull();
  });

  it("renders markup as literal text", () => {
    const { container } = render(<PsychometricResultDetails result={{ strengths: ["<img src=x onerror=alert(1)>"], counsellor_remarks: "<script>alert(1)</script>" }} />);
    expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeTruthy();
    expect(screen.getByText("<script>alert(1)</script>")).toBeTruthy();
    expect(container.querySelector("img, script")).toBeNull();
  });
});

describe("PsychometricResultsList", () => {
  it("renders a disclosure per assessment with results and a plain line for one without", () => {
    render(<PsychometricResultsList assessments={[{ id: "a", assessment_type: "Aptitude Test", ...FULL }, { id: "b", assessment_type: "Interest Inventory" }]} />);
    expect(screen.getByText("Aptitude Test — results", { selector: "summary" })).toBeTruthy();
    expect(screen.getByText("Interest Inventory: no results recorded yet.")).toBeTruthy();
    expect(screen.getAllByRole("group")).toHaveLength(1); // <details> has the implicit "group" role
  });
});
