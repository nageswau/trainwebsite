import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminTelecallerRow from "@/components/AdminTelecallerRow";
import type { TelecallerAdminRow } from "@/lib/telecaller";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const row: TelecallerAdminRow = {
  id: "t1", full_name: "Ravi", email: "ravi@x.local", phone: null, active: true, team: "overseas", employee_id: "T-1",
  reporting_manager: { id: "m1", full_name: "Meena", active: false }, manager_active: false,
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function table(ui: React.ReactNode) {
  return render(<table><tbody>{ui}</tbody></table>);
}

describe("AdminTelecallerRow (tel-001 §6.3)", () => {
  it("shows the team and flags an inactive manager", () => {
    table(<AdminTelecallerRow row={row} role="overseas_admin" onChanged={() => {}} />);
    expect(screen.getByText("Overseas")).toBeInTheDocument();
    expect(screen.getByText("No active manager")).toBeInTheDocument();
  });

  it("edits Employee ID with the team read-only and keeps the current manager", async () => {
    const mock = vi.fn().mockResolvedValue(res({ ok: true }));
    vi.stubGlobal("fetch", mock);
    const onChanged = vi.fn();
    table(<AdminTelecallerRow row={row} role="overseas_admin" onChanged={onChanged} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit Ravi" }));
    expect(screen.getByText("Overseas (cannot be changed here)")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Employee ID (required)"), { target: { value: "T-2" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Saved Ravi."));
    expect(JSON.parse(mock.mock.calls[0][1].body)).toEqual({
      full_name: "Ravi", phone: null, telecaller_profile: { employee_id: "T-2", reporting_manager_user_id: "m1" },
    });
  });

  it("Deactivate opens the reassignment group instead of a plain PATCH (tel-025)", async () => {
    const mock = vi.fn().mockResolvedValue(res({ leads: 0, follow_ups: 0, appointments: 0 }));
    vi.stubGlobal("fetch", mock);
    table(<AdminTelecallerRow row={row} role="overseas_admin" onChanged={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Deactivate Ravi" }));
    expect(await screen.findByRole("group", { name: "Deactivate Ravi" })).toBeInTheDocument();
    expect(String(mock.mock.calls[0][0])).toBe("/api/v1/admin/telecallers/t1/open-work");
    expect(mock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(false);
    fireEvent.click(await screen.findByRole("button", { name: "Keep active" }));
    expect(screen.queryByRole("group", { name: "Deactivate Ravi" })).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Deactivate Ravi" })).toHaveFocus());
  });

  it("offers Move team only to an admin who manages both teams (LC1)", () => {
    const { unmount } = table(<AdminTelecallerRow row={row} role="overseas_admin" onChanged={() => {}} />);
    expect(screen.queryByRole("button", { name: "Move Ravi to another team" })).not.toBeInTheDocument();
    unmount();
    table(<AdminTelecallerRow row={row} role="super_admin" onChanged={() => {}} />);
    expect(screen.getByRole("button", { name: "Move Ravi to another team" })).toBeInTheDocument();
  });

  it("an inactive row offers Reactivate and Reassign open work (LC4)", async () => {
    const mock = vi.fn().mockResolvedValue(res({ ok: true }));
    vi.stubGlobal("fetch", mock);
    const onChanged = vi.fn();
    table(<AdminTelecallerRow row={{ ...row, active: false }} role="super_admin" onChanged={onChanged} />);
    expect(screen.queryByRole("button", { name: "Deactivate Ravi" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reassign Ravi's open leads" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reactivate Ravi" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Reactivated Ravi."));
    expect(JSON.parse(mock.mock.calls[0][1].body)).toEqual({ active: true });
  });

  it("clears a failed reactivate's error when Edit opens", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail: "Cannot reactivate" }, 409)));
    table(<AdminTelecallerRow row={{ ...row, active: false }} role="super_admin" onChanged={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Reactivate Ravi" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Cannot reactivate");
    fireEvent.click(screen.getByRole("button", { name: "Edit Ravi" }));
    expect(screen.queryByText("Cannot reactivate")).not.toBeInTheDocument();
  });

  it("shows a failed save in the edit form's alert, focuses it and does not report a change", async () => {
    const mock = vi.fn().mockResolvedValue(res({ detail: "Employee ID already exists" }, 409));
    vi.stubGlobal("fetch", mock);
    const onChanged = vi.fn();
    table(<AdminTelecallerRow row={row} role="overseas_admin" onChanged={onChanged} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit Ravi" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    const alert = await screen.findByText("Employee ID already exists");
    expect(alert).toHaveAttribute("role", "alert");
    await waitFor(() => expect(alert).toHaveFocus());
    expect(onChanged).not.toHaveBeenCalled();
  });

  it("closes the edit form on Escape without any request", () => {
    const mock = vi.fn();
    vi.stubGlobal("fetch", mock);
    table(<AdminTelecallerRow row={row} role="overseas_admin" onChanged={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit Ravi" }));
    fireEvent.keyDown(screen.getByLabelText("Employee ID (required)"), { key: "Escape" });
    expect(screen.getByRole("button", { name: "Edit Ravi" })).toBeInTheDocument();
    expect(mock).not.toHaveBeenCalled();
  });

  // tel-001 QA-03: the notice names the telecaller as saved, not as they were before the edit.
  it("announces the saved name after a rename", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ ok: true })));
    const onChanged = vi.fn();
    table(<AdminTelecallerRow row={row} role="overseas_admin" onChanged={onChanged} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit Ravi" }));
    fireEvent.change(screen.getByLabelText("Full name (required)"), { target: { value: "Ravi Kumar" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Saved Ravi Kumar."));
  });

  // tel-001 QA-04: every cell carries its column label, so the phone layout can show each value as a labelled line.
  it("labels each cell for the stacked phone layout", () => {
    table(<AdminTelecallerRow row={row} role="overseas_admin" onChanged={() => {}} />);
    const labels = Array.from(document.querySelectorAll("td")).map((td) => td.getAttribute("data-label"));
    expect(labels).toEqual(["Name", "Employee ID", "Team", "Manager", "Status", "Actions"]);
  });
});
