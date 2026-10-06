import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminBdmRow from "@/components/AdminBdmRow";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const row = {
  id: "b1", full_name: "Asha", email: "a@x.local", phone: null, active: true, bdm_type: "college" as const, employee_id: "E-1", designation: null,
  department: null, territory: "Kochi", reporting_manager: { id: "m1", full_name: "Meera", active: true }, manager_active: true,
};
const managerPage = { items: [{ id: "m2", full_name: "Ravi", email: "ravi@x.local" }], total: 1, limit: 20, offset: 0 };

/** Picker searches get one manager (Ravi); every PATCH gets `patch`. */
function route(patch: Response = res({ ok: true })) {
  const mock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>((url) => Promise.resolve(String(url).startsWith("/api/v1/admin/bdm-managers") ? res(managerPage) : patch.clone()));
  vi.stubGlobal("fetch", mock);
  return mock;
}
const patches = (mock: ReturnType<typeof route>) => mock.mock.calls.filter(([, init]) => init?.method === "PATCH");
const patchBody = (mock: ReturnType<typeof route>, index = 0) => JSON.parse(String(patches(mock)[index][1]?.body));

function mount(overrides: Partial<typeof row> = {}, onChanged = vi.fn()) {
  render(<table><tbody><AdminBdmRow row={{ ...row, ...overrides }} onChanged={onChanged} /></tbody></table>);
  return onChanged;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AdminBdmRow (bdm-001 AC13)", () => {
  it("edits inline with the type read-only, and focuses the first field", async () => {
    route();
    mount();
    fireEvent.click(screen.getByRole("button", { name: "Edit Asha" }));
    await waitFor(() => expect(screen.getByLabelText("Full name (required)")).toHaveFocus());
    expect(screen.queryByLabelText(/Module/)).toBeNull();
    expect(screen.getByText("College (cannot be changed)")).toBeInTheDocument();
  });

  it("Esc cancels and returns focus to Edit", async () => {
    route();
    mount();
    fireEvent.click(screen.getByRole("button", { name: "Edit Asha" }));
    fireEvent.keyDown(screen.getByLabelText("Full name (required)"), { key: "Escape" });
    await waitFor(() => expect(screen.getByRole("button", { name: "Edit Asha" })).toHaveFocus());
  });

  it("starts the picker on the current manager, so an unrelated save keeps it (QA-02)", async () => {
    const mock = route();
    mount();
    fireEvent.click(screen.getByRole("button", { name: "Edit Asha" }));
    expect(screen.getByRole("combobox", { name: "Reporting manager (required)" })).toHaveValue("Meera");
    fireEvent.change(screen.getByLabelText("Territory"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(patches(mock)).toHaveLength(1));
    expect(patchBody(mock)).toEqual({
      full_name: "Asha", phone: null,
      bdm_profile: { employee_id: "E-1", designation: null, department: null, territory: null, reporting_manager_user_id: "m1" },
    });
  });

  it("labels an inactive current manager and still keeps it on save", async () => {
    const mock = route();
    mount({ manager_active: false, reporting_manager: { id: "m9", full_name: "Old Boss", active: false } });
    fireEvent.click(screen.getByRole("button", { name: "Edit Asha" }));
    expect(screen.getByRole("combobox", { name: "Reporting manager (required)" })).toHaveValue("Old Boss (inactive)");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(patches(mock)).toHaveLength(1));
    expect(patchBody(mock).bdm_profile.reporting_manager_user_id).toBe("m9");
  });

  it("can search for and pick a different manager", async () => {
    const mock = route();
    const onChanged = mount();
    fireEvent.click(screen.getByRole("button", { name: "Edit Asha" }));
    const combo = screen.getByRole("combobox", { name: "Reporting manager (required)" });
    fireEvent.change(combo, { target: { value: "rav" } });
    fireEvent.click(await screen.findByRole("option", { name: "Ravi — ravi@x.local" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Saved Asha."));
    expect(patchBody(mock).bdm_profile.reporting_manager_user_id).toBe("m2");
  });

  it("returns focus to Edit after a successful save (QA-06)", async () => {
    route();
    mount();
    fireEvent.click(screen.getByRole("button", { name: "Edit Asha" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Edit Asha" })).toHaveFocus());
  });

  it("keeps the form open on a 409 and moves focus to the message, so Esc still works (QA-06)", async () => {
    route(res({ detail: "Employee ID already exists" }, 409));
    const onChanged = mount();
    fireEvent.click(screen.getByRole("button", { name: "Edit Asha" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    const message = await screen.findByText("Employee ID already exists");
    await waitFor(() => expect(message).toHaveFocus());
    expect(onChanged).not.toHaveBeenCalled();
    fireEvent.keyDown(message, { key: "Escape" });
    await waitFor(() => expect(screen.getByRole("button", { name: "Edit Asha" })).toHaveFocus());
  });

  it("moves keyboard focus into the deactivate confirmation and back out of it", async () => {
    route();
    mount();
    fireEvent.click(screen.getByRole("button", { name: "Deactivate Asha" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Confirm deactivate" })).toHaveFocus());
    fireEvent.click(screen.getByRole("button", { name: "Keep active" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Deactivate Asha" })).toHaveFocus());
  });

  it("deactivation needs a second, explicit confirm, then focus lands on the row (QA-06)", async () => {
    const mock = route();
    const onChanged = mount();
    fireEvent.click(screen.getByRole("button", { name: "Deactivate Asha" }));
    expect(patches(mock)).toHaveLength(0);
    expect(screen.getByText(/can no longer sign in/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Confirm deactivate" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Deactivated Asha."));
    expect(patchBody(mock)).toEqual({ active: false });
    await waitFor(() => expect(document.activeElement).not.toBe(document.body));
    expect(document.activeElement?.closest("tr")).not.toBeNull();
  });

  it("a failed status change shows the message and focuses it", async () => {
    route(res({ detail: "Not allowed" }, 403));
    mount();
    fireEvent.click(screen.getByRole("button", { name: "Deactivate Asha" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm deactivate" }));
    const message = await screen.findByText("Not allowed");
    await waitFor(() => expect(message).toHaveFocus());
  });

  it("shows status in words and offers Reactivate for an inactive BDM", () => {
    route();
    mount({ active: false });
    expect(screen.getByText("Inactive")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reactivate Asha" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Deactivate Asha" })).toBeNull();
  });

  // tel-001 QA follow-up (QA-03 on the BDM page): the notice names the BDM as saved, not as they were before the edit.
  it("announces the saved name after a rename", async () => {
    route();
    const onChanged = mount();
    fireEvent.click(screen.getByRole("button", { name: "Edit Asha" }));
    fireEvent.change(screen.getByLabelText("Full name (required)"), { target: { value: "Asha Rao" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Saved Asha Rao."));
  });

  // QA-04 on the BDM page: every cell carries its column label for the stacked phone layout.
  it("labels each cell for the stacked phone layout", () => {
    mount();
    const labels = Array.from(document.querySelectorAll("td")).map((td) => td.getAttribute("data-label"));
    expect(labels).toEqual(["Name", "Employee ID", "Module", "Territory", "Manager", "Status", "Actions"]);
  });
});
