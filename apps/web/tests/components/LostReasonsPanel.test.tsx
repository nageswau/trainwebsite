import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import LostReasonsPanel from "@/components/LostReasonsPanel";

// ccrm-006 (D8): the manager's lost-reason list -- Browser QA-01 (a pager past one page) and QA-02 (focus stays on the row).
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const reason = (n: number, active = true) => ({ id: `r${n}`, name: `Reason ${n}`, active, sort_order: n });

let rows: ReturnType<typeof reason>[];
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  rows = [reason(1)];
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "PATCH") {
      const body = JSON.parse(String(init.body));
      rows = rows.map((r) => (url.endsWith(`/${r.id}`) ? { ...r, ...body } : r));
      return Promise.resolve(res(rows[0]));
    }
    const offset = Number(new URL(url, "http://x").searchParams.get("offset") ?? 0);
    const limit = Number(new URL(url, "http://x").searchParams.get("limit"));
    return Promise.resolve(res({ items: rows.slice(offset, offset + limit), total: rows.length, limit, offset }));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("LostReasonsPanel (ccrm-006)", () => {
  it("pages past the first page (QA-01)", async () => {
    rows = Array.from({ length: 105 }, (_, i) => reason(i + 1)); // tel-002's page size is 100
    render(<LostReasonsPanel />);
    const pager = await screen.findByRole("navigation", { name: "Lost reason pages" });
    expect(pager).toHaveTextContent("Showing 1–100 of 105");
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    await waitFor(() => expect(pager).toHaveTextContent("Showing 101–105 of 105"));
    expect(screen.getByText("Reason 105")).toBeTruthy();
  });

  it("keeps keyboard focus on the row after Deactivate and after closing the edit form (QA-02)", async () => {
    render(<LostReasonsPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Deactivate Reason 1" }));
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: "Reactivate Reason 1" })));
    fireEvent.click(screen.getByRole("button", { name: "Edit Reason 1" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: "Edit Reason 1" })));
  });
});
