import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentStudentsPanel from "@/components/AgentStudentsPanel";

// AGN-018 QA18-01: the staff sidebar's "Add" is a client navigation to ?new=1, and it is clicked again after the form was opened and
// closed. This models the App Router: useSearchParams changes only through the router (push/replace); a raw history.replaceState
// carrying Next's own history state does not reach it (the browser-QA failure: the second Add changed nothing).
let routerSearch = "";
const replace = vi.fn((url: string) => {
  routerSearch = new URL(url, "http://x").search.slice(1);
  window.history.replaceState(null, "", url);
});
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(routerSearch),
  useRouter: () => ({ replace, push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/overseas/agent/students",
}));

const res = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  replace.mockClear();
  routerSearch = "";
  window.history.replaceState(null, "", "/");
});

async function sidebarAdd(rerender: (ui: React.ReactElement) => void) {
  routerSearch = "new=1";
  window.history.pushState(null, "", "/overseas/agent/students?new=1");
  await act(async () => rerender(<AgentStudentsPanel memberRole="staff" />));
}

describe("AgentStudentsPanel and the sidebar's Add link (AGN-018)", () => {
  it("opens the add form on every Add, through the router, and leaves no new=1 behind", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ items: [], total: 0, limit: 20, offset: 0 }))));
    window.history.replaceState(null, "", "/overseas/agent/students");
    const { rerender } = render(<AgentStudentsPanel memberRole="staff" />);
    expect(await screen.findByText(/No students yet/)).toBeInTheDocument();

    await sidebarAdd(rerender);
    expect(await screen.findByRole("form", { name: "Add student" })).toBeInTheDocument();
    await act(async () => rerender(<AgentStudentsPanel memberRole="staff" />));

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("form", { name: "Add student" })).toBeNull();

    await sidebarAdd(rerender);
    expect(await screen.findByRole("form", { name: "Add student" })).toBeInTheDocument();
    expect(routerSearch).toBe("");
  });
});
