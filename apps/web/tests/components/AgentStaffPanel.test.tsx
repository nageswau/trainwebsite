import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentStaffPanel from "@/components/AgentStaffPanel";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const staff = (n: number) => ({ id: `s${n}`, code: `ABC-S${String(n).padStart(3, "0")}`, full_name: `Staff ${n}`, email: `s${n}@example.local`, phone: null, status: "active", setup: null });
const page = (items: unknown[], total = items.length, offset = 0) => ({ items, total, limit: 20, offset });
const twenty = () => Array.from({ length: 20 }, (_, i) => staff(i + 1));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AgentStaffPanel (AGN-002)", () => {
  it("shows loading, then the list", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res(page([staff(1)]))));
    render(<AgentStaffPanel />);
    expect(screen.getByText("Loading staff…")).toBeInTheDocument();
    expect(await screen.findByText("ABC-S001")).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Staff pages" })).toBeNull();
  });

  it("shows an empty state", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res(page([]))));
    render(<AgentStaffPanel />);
    expect(await screen.findByText("No staff yet. Add your first staff member below.")).toBeInTheDocument();
  });

  it("shows an error with Retry, including for a non-page body", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(res({ detail: "boom" }, 500)).mockResolvedValueOnce(res("<html>", 200)).mockResolvedValueOnce(res(page([staff(1)]))));
    render(<AgentStaffPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    expect(await screen.findByText("ABC-S001")).toBeInTheDocument();
  });

  it("pages through staff", async () => {
    const mock = vi.fn().mockResolvedValueOnce(res(page(twenty(), 21))).mockResolvedValueOnce(res(page([staff(21)], 21, 20)));
    vi.stubGlobal("fetch", mock);
    render(<AgentStaffPanel />);
    const pager = await screen.findByRole("navigation", { name: "Staff pages" });
    expect(within(pager).getByText("Showing 1–20 of 21")).toBeInTheDocument();
    expect(within(pager).getByRole("button", { name: "Previous page" })).toBeDisabled();
    fireEvent.click(within(pager).getByRole("button", { name: "Next page" }));
    expect(await screen.findByText("ABC-S021")).toBeInTheDocument();
    expect(mock.mock.calls[1][0]).toBe("/api/v1/workflows/overseas/agent/team/staff?limit=20&offset=20");
  });

  it("steps back a page when the current page comes back empty", async () => {
    const mock = vi.fn()
      .mockResolvedValueOnce(res(page(twenty(), 21)))
      .mockResolvedValueOnce(res(page([], 20, 20)))
      .mockResolvedValueOnce(res(page(twenty(), 20)));
    vi.stubGlobal("fetch", mock);
    render(<AgentStaffPanel />);
    fireEvent.click(within(await screen.findByRole("navigation", { name: "Staff pages" })).getByRole("button", { name: "Next page" }));
    await vi.waitFor(() => expect(mock).toHaveBeenCalledTimes(3));
    expect(mock.mock.calls[2][0]).toBe("/api/v1/workflows/overseas/agent/team/staff?limit=20&offset=0");
    expect(await screen.findByText("ABC-S001")).toBeInTheDocument();
  });

  it("announces a row change and reloads", async () => {
    const mock = vi.fn()
      .mockResolvedValueOnce(res(page([staff(1)])))
      .mockResolvedValueOnce(res({ member: { ...staff(1), status: "deactivated" } }))
      .mockResolvedValueOnce(res(page([{ ...staff(1), status: "deactivated" }])));
    vi.stubGlobal("fetch", mock);
    render(<AgentStaffPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Deactivate Staff 1" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm deactivate" }));
    expect(await screen.findByText("ABC-S001 Staff 1 deactivated. They have been signed out.")).toBeInTheDocument();
    expect(await screen.findByText("Deactivated")).toBeInTheDocument();
  });
});
