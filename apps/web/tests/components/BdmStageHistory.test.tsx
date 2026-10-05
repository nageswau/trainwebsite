import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmStageHistory from "@/components/BdmStageHistory";
import type { StageEvent } from "@/lib/bdmPipeline";

const event = (id: string, over: Partial<StageEvent> = {}): StageEvent => ({
  id, kind: "move", from_stage: "prospect", from_label: "College Prospect", to_stage: "contacted", to_label: "Contacted", note: null,
  actor: { id: "b1", full_name: "Asha" }, created_at: "2026-10-05T10:00:00Z", ...over,
});
const page = (items: StageEvent[], total = items.length, offset = 0) => ({ items, total, limit: 20, offset });
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("BdmStageHistory (bdm-004 §8.2)", () => {
  it("lists moves, Lost and Revive with actor and note", () => {
    render(<BdmStageHistory orgId="o1" initial={page([event("e2", { kind: "lost", from_label: "Contacted", to_label: "Contacted", note: "No budget" }), event("e1", { note: "First call" })])} version={0} />);
    const list = screen.getByRole("list", { name: "Stage history" });
    const [lost, moved] = within(list).getAllByRole("listitem");
    expect(lost).toHaveTextContent("Marked lost at Contacted");
    expect(lost).toHaveTextContent("Reason: No budget");
    expect(moved).toHaveTextContent("College Prospect → Contacted");
    expect(moved).toHaveTextContent("By Asha");
    expect(moved).toHaveTextContent("Note: First call");
  });

  it("says when there is no history yet", () => {
    render(<BdmStageHistory orgId="o1" initial={page([])} version={0} />);
    expect(screen.getByText("No stage changes yet.")).toBeInTheDocument();
  });

  it("loads more without repeating rows", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res(page([event("e1"), event("e0")], 3, 1))));
    render(<BdmStageHistory orgId="o1" initial={page([event("e2"), event("e1")], 3)} version={0} />);
    fireEvent.click(screen.getByRole("button", { name: "Show more" }));
    await waitFor(() => expect(screen.getAllByRole("listitem")).toHaveLength(3));
    expect(screen.queryByRole("button", { name: "Show more" })).toBeNull();
  });

  it("reloads the first page when the organization changes", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res(page([event("e9", { to_label: "Meeting" })])));
    vi.stubGlobal("fetch", fetchMock);
    const { rerender } = render(<BdmStageHistory orgId="o1" initial={page([])} version={0} />);
    rerender(<BdmStageHistory orgId="o1" initial={page([])} version={1} />);
    await waitFor(() => expect(screen.getByText("College Prospect → Meeting")).toBeInTheDocument());
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/bdm/organizations/o1/stage-history?limit=20&offset=0");
  });

  it("a failed first load offers Try again", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res(page([event("e1")]))));
    render(<BdmStageHistory orgId="o1" initial={null} version={0} />);
    expect(screen.getByText("Unable to load the stage history.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.getByText("College Prospect → Contacted")).toBeInTheDocument());
  });
});
