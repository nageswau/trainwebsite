import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SchoolSkillScores from "@/components/SchoolSkillScores";

import { detail, enrolment, json, stubFetch } from "./skillFixtures";

// ENH-011 spec §7: assessments and a labelled score grid (out of the assessment's maximum), with remarks; a read-only view on a
// closed batch.
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh }) }));

const SPEECH = { id: "a1", name: "Speech", max_score: 20 };
const withAssessment = (over = {}) =>
  detail({ assessments: [SPEECH], enrollments: [enrolment("1", { scores: [{ assessment_id: "a1", score: 15, remarks: "Pace" }] }), enrolment("2"), enrolment("3", { status: "withdrawn" })], ...over });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  refresh.mockReset();
});

describe("SchoolSkillScores", () => {
  it("explains what an assessment is for when there are none", () => {
    render(<SchoolSkillScores batch={detail()} />);
    expect(screen.getByText(/No assessments yet/)).toBeTruthy();
  });

  it("adds an assessment", async () => {
    const fetchMock = stubFetch(() => json({ id: "a2", name: "Final project", max_score: 100 }, 201));
    render(<SchoolSkillScores batch={detail()} />);
    fireEvent.change(screen.getByLabelText("Assessment name"), { target: { value: "Final project" } });
    fireEvent.change(screen.getByLabelText("Maximum score"), { target: { value: "100" } });
    fireEvent.click(screen.getByRole("button", { name: "Add assessment" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({ name: "Final project", max_score: 100 });
  });

  it("labels each score with the student and maximum, prefilled with saved scores, and skips students who cannot be scored", () => {
    render(<SchoolSkillScores batch={withAssessment()} />);
    expect((screen.getByLabelText("Score for Student 1 (out of 20)") as HTMLInputElement).value).toBe("15");
    expect((screen.getByLabelText("Remarks for Student 1 (optional)") as HTMLInputElement).value).toBe("Pace");
    expect(screen.queryByLabelText(/Score for Student 3/)).toBeNull();
  });

  it("blocks a score above the maximum on the field itself", () => {
    const fetchMock = stubFetch(() => json({}));
    render(<SchoolSkillScores batch={withAssessment()} />);
    const input = screen.getByLabelText("Score for Student 2 (out of 20)");
    fireEvent.change(input, { target: { value: "21" } });
    fireEvent.click(screen.getByRole("button", { name: "Save scores" }));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(input.getAttribute("aria-invalid")).toBe("true");
    expect(document.getElementById(input.getAttribute("aria-describedby")!)!.textContent).toBe("Enter a score from 0 to 20");
  });

  it("saves the entered scores only, with remarks", async () => {
    const fetchMock = stubFetch(() => json({ ...SPEECH, scores: [] }));
    render(<SchoolSkillScores batch={withAssessment()} />);
    fireEvent.change(screen.getByLabelText("Score for Student 2 (out of 20)"), { target: { value: "18.5" } });
    fireEvent.change(screen.getByLabelText("Remarks for Student 2 (optional)"), { target: { value: " Improve eye contact " } });
    fireEvent.click(screen.getByRole("button", { name: "Save scores" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/school/career-counselor/skill-assessments/a1/scores");
    expect(JSON.parse(String(init?.body))).toEqual({ scores: [{ enrollment_id: "e1", score: 15, remarks: "Pace" }, { enrollment_id: "e2", score: 18.5, remarks: "Improve eye contact" }] });
  });

  it("is read-only on a closed batch", () => {
    render(<SchoolSkillScores batch={withAssessment({ status: "closed" })} />);
    expect(screen.queryByRole("button", { name: "Add assessment" })).toBeNull();
    expect(screen.queryByRole("spinbutton")).toBeNull();
    expect(screen.getByText("Student 1: 15 / 20 (Pace)")).toBeTruthy();
    expect(screen.getByText("Student 2: not scored")).toBeTruthy();
  });
});
