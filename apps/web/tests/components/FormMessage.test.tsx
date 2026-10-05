import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import FormMessage from "@/components/FormMessage";

const scrollIntoView = vi.fn();

beforeEach(() => {
  scrollIntoView.mockReset();
  Element.prototype.scrollIntoView = scrollIntoView;
});

afterEach(cleanup);

// QA-022-04: on a phone a refusal rendered under the submit button can land below the fold; it must be brought into view
// (without moving focus, which stays on the control the user used).
describe("FormMessage", () => {
  it("brings a failure into view without taking focus", () => {
    const button = document.createElement("button");
    document.body.appendChild(button);
    button.focus();
    render(<FormMessage message={{ text: "This school has no active partnership tier.", failed: true }} />);
    expect(screen.getByRole("alert")).toHaveTextContent("This school has no active partnership tier.");
    expect(scrollIntoView).toHaveBeenCalledWith({ block: "nearest" });
    expect(document.activeElement).toBe(button);
    button.remove();
  });

  it("scrolls again when a new failure replaces the old one", () => {
    const { rerender } = render(<FormMessage message={{ text: "First", failed: true }} />);
    rerender(<FormMessage message={{ text: "Second", failed: true }} />);
    expect(scrollIntoView).toHaveBeenCalledTimes(2);
  });

  it("leaves a success message where it is", () => {
    render(<FormMessage message={{ text: "Saved.", failed: false }} />);
    expect(screen.getByRole("status")).toHaveTextContent("Saved.");
    expect(scrollIntoView).not.toHaveBeenCalled();
  });
});
