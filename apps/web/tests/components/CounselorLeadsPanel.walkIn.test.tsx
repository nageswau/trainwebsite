import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CounselorLeadsPanel from "@/components/CounselorLeadsPanel";

// csc-004 (DEC-SCOPE-229): only the overseas counselor records walk-in leads (W1); the IT counselor's My leads is unchanged.
beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [], total: 0, limit: 20, offset: 0 }), { status: 200 })));
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
