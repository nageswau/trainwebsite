import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }), usePathname: () => "/school/career-counselor/dashboard" }));

import Loading from "@/app/school/career-counselor/dashboard/loading";

afterEach(cleanup);

// QA-10 (browser QA 2026-09-28): the skeleton replaced the whole screen, sidebar and header included, so the layout flashed on
// every client navigation. It now renders inside the portal shell, like the parent pages' own loading screen.
describe("career counsellor dashboard loading state", () => {
  it("keeps the portal navigation while showing the busy skeleton", () => {
    render(<Loading />);
    expect(screen.getAllByRole("link", { name: "Dashboard" }).length).toBeGreaterThan(0);
    expect(screen.getByLabelText("Loading career records")).toHaveAttribute("aria-busy", "true");
  });
});
