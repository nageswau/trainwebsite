import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import NavGroup from "@/components/NavGroup";

// QA8-05: a filter click gives immediate feedback while the server navigation runs. The push returns a promise that never settles,
// so the transition stays pending (React 19 keeps an async transition pending until its promise resolves).
const push = vi.fn((href: string) => {
  void href;
  return new Promise<void>(() => {});
});
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(""),
}));

const item = {
  href: "/overseas/agent/applications",
  label: "Applications",
  children: [
    { href: "/overseas/agent/applications?status=draft", label: "Draft" },
    { href: "/overseas/agent/applications?status=offer", label: "Offer received" },
  ],
};

afterEach(() => {
  cleanup();
  push.mockClear();
});

describe("NavGroup pending filter (AGN-008 QA8-05)", () => {
  it("marks the clicked filter busy with a Loading suffix while the navigation is pending", async () => {
    render(<NavGroup item={item} pathname="/overseas/agent/applications" />);
    const link = screen.getByRole("link", { name: "Offer received" });
    expect(link).toHaveAttribute("href", "/overseas/agent/applications?status=offer");
    fireEvent.click(link);
    expect(push).toHaveBeenCalledWith("/overseas/agent/applications?status=offer");
    expect(await screen.findByText("Loading…")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Offer received/ })).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("link", { name: "Draft" })).not.toHaveAttribute("aria-busy");
  });

  it("leaves a modified click (new tab) to the browser", () => {
    render(<NavGroup item={item} pathname="/overseas/agent/applications" />);
    fireEvent.click(screen.getByRole("link", { name: "Draft" }), { ctrlKey: true });
    fireEvent.click(screen.getByRole("link", { name: "Draft" }), { metaKey: true });
    fireEvent.click(screen.getByRole("link", { name: "Draft" }), { shiftKey: true });
    expect(push).not.toHaveBeenCalled();
    expect(screen.queryByText("Loading…")).toBeNull();
  });
});
