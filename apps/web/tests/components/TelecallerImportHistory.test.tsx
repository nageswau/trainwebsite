import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import TelecallerImportHistory from "@/components/TelecallerImportHistory";

// tel-006 (R11, spec §4): the past imports -- loading, rows, empty, error + Retry, and a reload after an upload.
const item = {
  id: "b1", campaign: { id: "c1", name: "Sep Instagram" }, division: "it", uploaded_by: { id: "u1", full_name: "Meera Manager" },
  total_rows: 3, created_count: 1, attached_count: 1, rejected_count: 1, created_at: "2026-10-06T10:00:00Z",
};
const page = (items: unknown[]) => ({ ok: true, status: 200, json: async () => ({ items, total: items.length, limit: 50, offset: 0 }) });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("TelecallerImportHistory", () => {
  it("shows a loading state, then each import with its counts", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(page([item])));
    render(<TelecallerImportHistory version={0} />);
    expect(screen.getByRole("status").textContent).toMatch(/Loading/);
    const table = await screen.findByRole("table");
    const cells = within(table).getAllByRole("row")[1].textContent;
    expect(cells).toContain("Sep Instagram");
    expect(cells).toContain("Meera Manager");
    expect(cells).toContain("1 created, 1 added to existing leads, 1 rejected");
  });

  it("says when there are no imports yet", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(page([])));
    render(<TelecallerImportHistory version={0} />);
    expect(await screen.findByText("No imports yet.")).toBeTruthy();
  });

  it("offers Retry after a failed load, and reloads when the version changes", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce({ ok: false, status: 500, json: async () => ({}) }).mockResolvedValue(page([item]));
    vi.stubGlobal("fetch", fetchMock);
    const { rerender } = render(<TelecallerImportHistory version={0} />);
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    await screen.findByRole("table");
    rerender(<TelecallerImportHistory version={1} />);
    await screen.findByRole("table");
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/telecaller/imports?limit=50");
  });
});
