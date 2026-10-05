import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminTelecallerPanel from "@/components/AdminTelecallerPanel";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => "/admin/telecallers",
  useSearchParams: () => new URLSearchParams(),
}));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const empty = { items: [], total: 0, limit: 50, offset: 0 };

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AdminTelecallerPanel (tel-001 §6.3)", () => {
  it("shows the empty state", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(res(String(url).includes("telecaller-managers") ? { ...empty, total: 1 } : empty))));
    render(<AdminTelecallerPanel role="super_admin" />);
    expect(await screen.findByText("No telecallers yet. Use the Create telecaller form to add the first one.")).toBeInTheDocument();
  });

  it("shows an error with Retry when the list fails", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(String(url).includes("telecaller-managers") ? res({ ...empty, total: 1 }) : res({ detail: "x" }, 500))));
    render(<AdminTelecallerPanel role="super_admin" />);
    expect(await screen.findByText("Unable to load telecallers.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("lists rows from the server", async () => {
    const page = { items: [{ id: "t1", full_name: "Ravi", email: "r@x", phone: null, active: true, team: "it", employee_id: "T-1", reporting_manager: { id: "m1", full_name: "Meena", active: true }, manager_active: true }], total: 1, limit: 50, offset: 0 };
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(res(String(url).includes("telecaller-managers") ? { ...empty, total: 1 } : page))));
    render(<AdminTelecallerPanel role="it_admin" />);
    expect(await screen.findByText("Ravi")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Telecallers" })).toBeInTheDocument();
  });
});
