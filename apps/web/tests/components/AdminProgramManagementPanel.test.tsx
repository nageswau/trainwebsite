import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AdminProgramManagementPanel from "@/components/AdminProgramManagementPanel";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

// rec-036 QA36-01/02: a program's Skills editor opens directly under its own row (not after a long table), Close returns focus to that
// row's Skills button, and filtering the row out of the search closes the editor with it.
const res = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });
const PROGRAMS = [
  { id: "P1", slug: "dotnet", category: "Software", title: ".NET", duration: "8w", fees: 0, active: true },
  { id: "P2", slug: "python-full-stack", category: "Software", title: "Python Full Stack", duration: "8w", fees: 0, active: true },
];

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(res(url === "/api/v1/admin/programs" ? PROGRAMS : { items: [] }))));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AdminProgramManagementPanel skills (rec-036)", () => {
  it("opens the editor in the row right under its program and returns focus on Close", async () => {
    render(<AdminProgramManagementPanel />);
    const button = await screen.findByRole("button", { name: "Skills for .NET" });
    fireEvent.click(button);
    expect(button.getAttribute("aria-expanded")).toBe("true");
    const rows = screen.getAllByRole("row");
    const programRow = rows.findIndex((r) => within(r).queryByRole("button", { name: "Skills for .NET" }));
    expect(within(rows[programRow + 1]).getByRole("region", { name: "Skills taught in .NET" })).toBeTruthy();
    fireEvent.click(await within(rows[programRow + 1]).findByRole("button", { name: "Close" }));
    expect(screen.queryByRole("region", { name: "Skills taught in .NET" })).toBeNull();
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: "Skills for .NET" })));
  });

  it("closes the editor when its program is filtered out of the search", async () => {
    render(<AdminProgramManagementPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Skills for .NET" }));
    await screen.findByRole("region", { name: "Skills taught in .NET" });
    fireEvent.change(screen.getByLabelText("Search by title, category, or slug"), { target: { value: "python" } });
    expect(screen.queryByRole("region", { name: "Skills taught in .NET" })).toBeNull();
    fireEvent.change(screen.getByLabelText("Search by title, category, or slug"), { target: { value: "" } });
    expect(screen.queryByRole("region", { name: "Skills taught in .NET" })).toBeNull();
  });
});
