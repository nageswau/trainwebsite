import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import PublicShell from "@/components/PublicShell";

// The header and footer are not what is under test; the shell's own structure is.
vi.mock("@/components/SiteHeader", () => ({ default: () => <header>site header</header> }));
vi.mock("@/components/Footer", () => ({ default: () => <footer>site footer</footer> }));

afterEach(cleanup);

// ENH-006 QA-008: reaching a form on any public page took 17 Tab presses through the site header, with no way past it.
describe("PublicShell skip link", () => {
  it("offers a skip link as the very first thing in the page, pointing at the main content", () => {
    const { container } = render(
      <PublicShell>
        <p>page content</p>
      </PublicShell>,
    );
    const skip = screen.getByRole("link", { name: "Skip to main content" });
    expect(skip).toHaveAttribute("href", "#main-content");
    expect(container.firstElementChild).toBe(skip);
  });

  it("gives the main landmark the id the skip link targets, and makes it programmatically focusable", () => {
    render(
      <PublicShell>
        <p>page content</p>
      </PublicShell>,
    );
    const main = screen.getByRole("main");
    expect(main).toHaveAttribute("id", "main-content");
    expect(main).toHaveAttribute("tabindex", "-1");
    expect(main).toHaveTextContent("page content");
  });

  it("keeps the header, the content and the footer, in that order", () => {
    const { container } = render(
      <PublicShell>
        <p>page content</p>
      </PublicShell>,
    );
    expect([...container.children].map((el) => el.tagName)).toEqual(["A", "HEADER", "MAIN", "FOOTER"]);
  });
});
