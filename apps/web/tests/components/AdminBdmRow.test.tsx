import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminBdmRow from "@/components/AdminBdmRow";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const row = {
  id: "b1", full_name: "Asha", email: "a@x.local", phone: null, active: true, bdm_type: "college" as const, employee_id: "E-1", designation: null,
  department: null, territory: "Kochi", reporting_manager: { id: "m1", full_name: "Meera", active: true }, manager_active: true,
};
const managers = [{ id: "m1", full_name: "Meera" }, { id: "m2", full_name: "Ravi" }];

function mount(overrides: Partial<typeof row> = {}, onChanged = vi.fn()) {
  render(<table><tbody><AdminBdmRow row={{ ...row, ...overrides }} managers={managers} onChanged={onChanged} /></tbody></table>);
  return onChanged;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AdminBdmRow (bdm-001 AC13)", () => {
  it("edits inline with the type read-only, and focuses the first field", async () => {
    mount();
    fireEvent.click(screen.getByRole("button", { name: "Edit Asha" }));
    await waitFor(() => expect(screen.getByLabelText("Full name (required)")).toHaveFocus());
    expect(screen.queryByLabelText(/Module/)).toBeNull();
    expect(screen.getByText("College (cannot be changed)")).toBeInTheDocument();
  });

  it("Esc cancels and returns focus to Edit", async () => {
    mount();
    fireEvent.click(screen.getByRole("button", { name: "Edit Asha" }));
    fireEvent.keyDown(screen.getByLabelText("Full name (required)"), { key: "Escape" });
    await waitFor(() => expect(screen.getByRole("button", { name: "Edit Asha" })).toHaveFocus());
  });

  it("saves user fields and profile in one PATCH, and reports only after success", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    const onChanged = mount();
    fireEvent.click(screen.getByRole("button", { name: "Edit Asha" }));
    fireEvent.change(screen.getByLabelText("Territory"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("Reporting manager (required)"), { target: { value: "m2" } });
    expect(onChanged).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Saved Asha."));
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/admin/users/b1");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toEqual({
      full_name: "Asha", phone: null,
      bdm_profile: { employee_id: "E-1", designation: null, department: null, territory: null, reporting_manager_user_id: "m2" },
    });
  });

  it("keeps the form open with the server's message on a 409", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail: "Employee ID already exists" }, 409)));
    const onChanged = mount();
    fireEvent.click(screen.getByRole("button", { name: "Edit Asha" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Employee ID already exists")).toBeInTheDocument();
    expect(screen.getByLabelText("Full name (required)")).toBeInTheDocument();
    expect(onChanged).not.toHaveBeenCalled();
  });

  it("lists an inactive current manager so an unrelated edit keeps it", () => {
    mount({ manager_active: false, reporting_manager: { id: "m9", full_name: "Old Boss", active: false } });
    fireEvent.click(screen.getByRole("button", { name: "Edit Asha" }));
    expect(screen.getByLabelText("Reporting manager (required)")).toHaveValue("m9");
    expect(screen.getByRole("option", { name: "Old Boss (inactive)" })).toBeInTheDocument();
  });

  it.each([
    ["the picker failed or is loading", null],
    ["the picker lacks the current (active) manager", [{ id: "m2", full_name: "Ravi" }]],
  ])("keeps the current manager selected when %s, so an unrelated save never reassigns", async (_label, list) => {
    const fetchMock = vi.fn().mockResolvedValue(res({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    render(<table><tbody><AdminBdmRow row={row} managers={list} onChanged={vi.fn()} /></tbody></table>);
    fireEvent.click(screen.getByRole("button", { name: "Edit Asha" }));
    expect(screen.getByLabelText("Reporting manager (required)")).toHaveValue("m1");
    fireEvent.change(screen.getByLabelText("Territory"), { target: { value: "Kollam" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(JSON.parse(fetchMock.mock.calls[0][1].body).bdm_profile.reporting_manager_user_id).toBe("m1");
  });

  it("lists the current manager once, not twice, when the picker includes it", () => {
    mount();
    fireEvent.click(screen.getByRole("button", { name: "Edit Asha" }));
    expect(screen.getAllByRole("option", { name: "Meera" })).toHaveLength(1);
  });

  it("moves keyboard focus into the deactivate confirmation and back out of it", async () => {
    mount();
    fireEvent.click(screen.getByRole("button", { name: "Deactivate Asha" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Confirm deactivate" })).toHaveFocus());
    fireEvent.click(screen.getByRole("button", { name: "Keep active" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Deactivate Asha" })).toHaveFocus());
  });

  it("deactivation needs a second, explicit confirm", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    const onChanged = mount();
    fireEvent.click(screen.getByRole("button", { name: "Deactivate Asha" }));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByText(/can no longer sign in/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Confirm deactivate" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Deactivated Asha."));
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ active: false });
  });

  it("shows status in words and offers Reactivate for an inactive BDM", () => {
    mount({ active: false });
    expect(screen.getByText("Inactive")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reactivate Asha" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Deactivate Asha" })).toBeNull();
  });
});
