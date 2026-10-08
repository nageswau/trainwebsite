import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import UniversityActions from "@/components/UniversityActions";
import UniversityAssignForm from "@/components/UniversityAssignForm";
import type { University } from "@/lib/universities";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh }) }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const all = { can_edit: true, can_assign: true, can_publish: true, can_deactivate: true, can_edit_contacts: true };
const uni = (over: Partial<University> = {}) => ({ id: "u1", name: "ABC", active: true, catalogue_visible: false, application_count: 0, permissions: all,
  primary_manager: null, backup_manager: null, ...over }) as University;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  refresh.mockReset();
});

describe("UniversityActions (upc-003 UM5, UM10)", () => {
  it("publishes an internal university", async () => {
    const mock = vi.fn(() => Promise.resolve(res({ university: { id: "u1" } })));
    vi.stubGlobal("fetch", mock);
    render(<UniversityActions university={uni()} />);
    fireEvent.click(screen.getByRole("button", { name: "Publish to catalogue" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(mock).toHaveBeenCalledWith("/api/v1/partnership/universities/u1/publish", expect.objectContaining({ method: "POST" }));
  });

  it("shows why publishing was refused", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "Add an overview before publishing" }, 422))));
    render(<UniversityActions university={uni()} />);
    fireEvent.click(screen.getByRole("button", { name: "Publish to catalogue" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Add an overview before publishing");
    expect(refresh).not.toHaveBeenCalled();
  });

  it("confirms deactivation and warns about applications before sending confirm", async () => {
    const mock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(() => Promise.resolve(res({ university: { id: "u1" } })));
    vi.stubGlobal("fetch", mock);
    render(<UniversityActions university={uni({ application_count: 3 })} />);
    fireEvent.click(screen.getByRole("button", { name: "Deactivate" }));
    expect(screen.getByText(/3 applications/)).toBeInTheDocument();
    expect(mock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Yes, deactivate" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(JSON.parse(String(mock.mock.calls[0][1]!.body))).toEqual({ confirm: true });
  });

  it("offers reactivate for an inactive university and nothing without rights", () => {
    const { rerender } = render(<UniversityActions university={uni({ active: false })} />);
    expect(screen.getByRole("button", { name: "Reactivate" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Publish to catalogue" })).not.toBeInTheDocument();
    rerender(<UniversityActions university={uni({ permissions: { ...all, can_publish: false, can_deactivate: false } })} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});

describe("UniversityAssignForm (upc-003 §27)", () => {
  it("assigns a primary and a backup from the team picker", async () => {
    const team = { items: [{ id: "m1", full_name: "Rahul", email: "rahul@x.local" }, { id: "m2", full_name: "Priya", email: "priya@x.local" }], total: 2, limit: 20, offset: 0 };
    const mock = vi.fn((url: string) => Promise.resolve(String(url).includes("manager-options") ? res(team) : res({ university: { id: "u1" } })));
    vi.stubGlobal("fetch", mock);
    render(<UniversityAssignForm university={uni()} />);
    for (const [name, pick] of [["Primary manager", "Rahul — rahul@x.local"], ["Backup manager", "Priya — priya@x.local"]]) {
      const combo = screen.getByRole("combobox", { name });
      fireEvent.focus(combo);
      fireEvent.change(combo, { target: { value: pick.slice(0, 3) } });
      fireEvent.click(await screen.findByRole("option", { name: pick }));
    }
    fireEvent.click(screen.getByRole("button", { name: "Save managers" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const post = mock.mock.calls.find(([url]) => String(url).endsWith("/assign"))!;
    expect(JSON.parse(String((post as unknown as [string, RequestInit])[1].body))).toEqual({ primary_manager_user_id: "m1", backup_manager_user_id: "m2" });
  });
});
