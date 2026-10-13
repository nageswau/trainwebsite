import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import UniversityLogo from "@/components/UniversityLogo";

afterEach(cleanup);
describe("UniversityLogo", () => {
  it("renders the logo image with the university name as alt text", () => {
    render(<UniversityLogo name="University of South Wales" logoUrl="/universities/logos/university-of-south-wales.png" />);
    expect(screen.getByRole("img", { name: "University of South Wales logo" }).getAttribute("src")).toContain("university-of-south-wales.png");
  });
  it("is hidden from assistive technology when decorative", () => {
    const { container } = render(<UniversityLogo name="University of South Wales" logoUrl={null} decorative />);
    expect(container.querySelector("[aria-hidden]")?.textContent).toBe("US");
    expect(screen.queryByRole("img")).toBeNull();
  });
  it("falls back to a monogram without a logo", () => {
    render(<UniversityLogo name="University of South Wales" logoUrl={null} />);
    expect(screen.getByLabelText("University of South Wales").textContent).toBe("US");
  });
});
