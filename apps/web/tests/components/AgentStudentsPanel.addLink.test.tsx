import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentStudentsPanel from "@/components/AgentStudentsPanel";

// AGN-018 final review: the staff sidebar's "Add" is a client navigation to ?new=1 -- the panel is already mounted when a staff
// member clicks it on My Students, so the form must open on the search-param change, not only on first load.
let search = "";
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(search) }));

const res = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  search = "";
  window.history.replaceState(null, "", "/");
});

describe("AgentStudentsPanel and the sidebar's Add link (AGN-018)", () => {
  it("opens the add form when ?new=1 arrives after mount, and drops it from the URL", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ items: [], total: 0, limit: 20, offset: 0 }))));
    window.history.replaceState(null, "", "/overseas/agent/students");
    const { rerender } = render(<AgentStudentsPanel memberRole="staff" />);
    expect(await screen.findByText(/No students yet/)).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Add student" })).toBeNull();

    search = "new=1";
    window.history.replaceState(null, "", "/overseas/agent/students?new=1");
    await act(async () => rerender(<AgentStudentsPanel memberRole="staff" />));
    expect(await screen.findByRole("form", { name: "Add student" })).toBeInTheDocument();
    await waitFor(() => expect(window.location.search).toBe(""));
  });
});
