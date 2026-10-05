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
    table(<AdminTelecallerRow row={row} onChanged={() => {}} />);
    expect(screen.getByText("Overseas")).toBeInTheDocument();
    expect(screen.getByText("No active manager")).toBeInTheDocument();
  });

  it("edits Employee ID with the team read-only and keeps the current manager", async () => {
    const mock = vi.fn().mockResolvedValue(res({ ok: true }));
    vi.stubGlobal("fetch", mock);
    const onChanged = vi.fn();
    table(<AdminTelecallerRow row={row} onChanged={onChanged} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit Ravi" }));
    expect(screen.getByText("Overseas (cannot be changed here)")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Employee ID (required)"), { target: { value: "T-2" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Saved Ravi."));
    expect(JSON.parse(mock.mock.calls[0][1].body)).toEqual({
      full_name: "Ravi", phone: null, telecaller_profile: { employee_id: "T-2", reporting_manager_user_id: "m1" },
    });
  });

  it("deactivates only after an inline confirm", async () => {
    const mock = vi.fn().mockResolvedValue(res({ ok: true }));
    vi.stubGlobal("fetch", mock);
    table(<AdminTelecallerRow row={row} onChanged={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Deactivate Ravi" }));
    expect(mock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Confirm deactivate" }));
    await waitFor(() => expect(JSON.parse(mock.mock.calls[0][1].body)).toEqual({ active: false }));
  });

  it("clears a failed deactivate's error when Edit opens", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail: "Cannot deactivate" }, 409)));
    table(<AdminTelecallerRow row={row} onChanged={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Deactivate Ravi" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm deactivate" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Cannot deactivate");
    fireEvent.click(screen.getByRole("button", { name: "Edit Ravi" }));
    expect(screen.queryByText("Cannot deactivate")).not.toBeInTheDocument();
  });

  it("shows a failed save in the edit form's alert, focuses it and does not report a change", async () => {
    const mock = vi.fn().mockResolvedValue(res({ detail: "Employee ID already exists" }, 409));
    vi.stubGlobal("fetch", mock);
    const onChanged = vi.fn();
    table(<AdminTelecallerRow row={row} onChanged={onChanged} />);
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
    table(<AdminTelecallerRow row={row} onChanged={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit Ravi" }));
    fireEvent.keyDown(screen.getByLabelText("Employee ID (required)"), { key: "Escape" });
    expect(screen.getByRole("button", { name: "Edit Ravi" })).toBeInTheDocument();
    expect(mock).not.toHaveBeenCalled();
  });
});
