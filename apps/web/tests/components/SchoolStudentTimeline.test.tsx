import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SchoolStudentTimeline, { type TimelineEvent } from "@/components/SchoolStudentTimeline";

// `serverApi` reads next/headers cookies, so it is mocked (same as the other server-component tests).
vi.mock("@/lib/api", () => ({ serverApi: vi.fn() }));

const at = "2026-09-19T10:00:00Z";
// The API (`GET /school/students/{id}/timeline`) emits these categories today; the component must render every one.
const emitted = [
  { category: "profile", label: "Profile" },
  { category: "career", label: "Career" },
  { category: "psychometric", label: "Psychometric" },
  { category: "academic", label: "Academic" },
  { category: "activity", label: "Activity" },
  { category: "test_prep", label: "Test prep" },
  { category: "foreign_language", label: "Foreign language" },
  { category: "global_education", label: "Global education" },
  { category: "soft_skills", label: "Soft skills" }, // ENH-011
  { category: "digital_skills", label: "Digital skills" }, // ENH-011
] as const;

afterEach(cleanup);

describe("SchoolStudentTimeline", () => {
  it("says so when there are no events", () => {
    render(<SchoolStudentTimeline events={[]} />);
    expect(screen.getByText("No journey events recorded yet.")).toBeTruthy();
  });

  it.each(emitted)("renders a $category event with a readable badge", ({ category, label }) => {
    const event = { date: at, category, type: "x", title: `Title ${category}`, detail: null } as TimelineEvent;
    render(<SchoolStudentTimeline events={[event]} />);
    expect(screen.getByText(`Title ${category}`)).toBeTruthy();
    expect(screen.getByText(label)).toBeTruthy();
  });

  it("does not crash on a category it does not know; it shows a humanised badge instead", () => {
    const event = { date: at, category: "visa_planning", type: "x", title: "Future stage", detail: null } as unknown as TimelineEvent;
    render(<SchoolStudentTimeline events={[event]} />);
    expect(screen.getByText("Future stage")).toBeTruthy();
    expect(screen.getByText("Visa planning")).toBeTruthy();
  });

  it.each(["soft_skills", "digital_skills"])("gives the ENH-011 %s category its own colour, not the unknown-category grey", (category) => {
    const event = { date: at, category, type: "skill_enrolled", title: "Enrolled", detail: null } as TimelineEvent;
    render(<SchoolStudentTimeline events={[event]} />);
    const badge = document.querySelector(".jtl-badge") as HTMLElement;
    expect(badge.style.getPropertyValue("--jtl-color")).not.toBe("#475569");
  });
});
