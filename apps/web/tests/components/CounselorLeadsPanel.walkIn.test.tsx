import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CounselorLeadsPanel from "@/components/CounselorLeadsPanel";

// csc-004 (DEC-SCOPE-229): only the overseas counselor records walk-in leads (W1); the IT counselor's My leads is unchanged.
// ccrm-012: the panel keeps its filters in the URL.
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }), usePathname: () => "/overseas/counselor/leads", useSearchParams: () => new URLSearchParams() }));
beforeEach(() => {
  // a fresh Response per call: the IT panel also reads the status labels (itc-005), and a body can be read only once
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify({ items: [], total: 0, limit: 20, offset: 0 }), { status: 200 }))));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("CounselorLeadsPanel walk-in entry (csc-004)", () => {
  it("offers New walk-in lead to the overseas counselor", async () => {
    render(<CounselorLeadsPanel division="overseas" />);
    expect(await screen.findByRole("link", { name: "New walk-in lead" })).toHaveAttribute("href", "/overseas/counselor/leads/new");
  });

  it("does not offer it to the IT counselor", async () => {
    render(<CounselorLeadsPanel division="it" />);
    await screen.findByText("No leads have been handed to you yet.");
    expect(screen.queryByRole("link", { name: "New walk-in lead" })).toBeNull();
  });
});
