import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentTasksBlock from "@/components/AgentTasksBlock";

const res = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AgentTasksBlock (AGN-016)", () => {
  it("titles the open New task form with a visible heading that names it (QA16-05)", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ items: [], total: 0, limit: 20, offset: 0 }))));
    render(<AgentTasksBlock view="open" />);
    fireEvent.click(await screen.findByRole("button", { name: "New task" }));
    const heading = screen.getByRole("heading", { level: 3, name: "New task" });
    expect(screen.getByRole("group", { name: "New task" })).toContainElement(heading);
  });

  it("uses a level below the student card's heading inside the card", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ items: [], total: 0, limit: 20, offset: 0 }))));
    render(<AgentTasksBlock view="all" studentId="s1" Heading="h6" />);
    fireEvent.click(await screen.findByRole("button", { name: "New task" }));
    expect(screen.getByRole("heading", { level: 6, name: "New task" })).toBeInTheDocument();
  });
});
