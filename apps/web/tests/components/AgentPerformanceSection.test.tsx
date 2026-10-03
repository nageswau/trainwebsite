import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentPerformanceSection from "@/components/AgentPerformanceSection";
import type { User } from "@/lib/types";

const base: User = { id: "u1", email: "m@example.test", full_name: "Mia Master", role: "agent", division: "overseas", profile: {} };

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AgentPerformanceSection (AGN-019)", () => {
  it("gives a Master the page title and the panel", () => {
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));
    render(<AgentPerformanceSection user={{ ...base, agent_member_role: "master" }} />);
    expect(screen.getByRole("heading", { level: 2, name: "Staff performance" })).toBeInTheDocument();
    expect(screen.getByRole("form", { name: "Staff performance filters" })).toBeInTheDocument();
  });

  it.each([
    ["staff", { ...base, agent_member_role: "staff" as const }],
    ["a non-agent", { ...base, role: "overseas_admin" }],
  ])("tells %s it is for Masters, without asking the server", (_, user) => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentPerformanceSection user={user} />);
    expect(screen.getByText("Staff performance is available to agency Masters.")).toBeInTheDocument();
    expect(screen.queryByRole("form")).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
