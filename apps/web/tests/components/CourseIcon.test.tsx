import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import CourseIcon from "@/components/CourseIcon";

afterEach(cleanup);
describe("CourseIcon (nehn-036 I7)", () => {
  it("draws the chosen icon, decorative", () => {
    const { container } = render(<CourseIcon icon="law" category="Computer Science" />);
    const svg = container.querySelector("svg")!;
    expect(svg.getAttribute("data-icon")).toBe("law");
    expect(svg.getAttribute("aria-hidden")).toBe("true");
    expect(svg.getAttribute("focusable")).toBe("false");
  });

  it("draws the subject default when no icon is chosen", () => {
    const { container } = render(<CourseIcon icon={null} category="Computer Science" />);
    expect(container.querySelector("svg")!.getAttribute("data-icon")).toBe("computing");
  });

  it("draws the general icon for an unknown subject", () => {
    const { container } = render(<CourseIcon category="Something new" />);
    expect(container.querySelector("svg")!.getAttribute("data-icon")).toBe("general");
  });

  it("has an inline and a card size", () => {
    const inline = render(<CourseIcon category="Law" />).container.querySelector("svg")!;
    expect(inline.getAttribute("width")).toBe("20");
    cleanup();
    const card = render(<CourseIcon category="Law" size="card" />).container.querySelector("svg")!;
    expect(card.getAttribute("width")).toBe("36");
    expect(card.getAttribute("class")).toContain("course-icon--card");
  });
});
