import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminPartnershipRow from "@/components/AdminPartnershipRow";
import type { PartnershipAdminRow } from "@/lib/partnership";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const row: PartnershipAdminRow = {
  id: "p1", full_name: "Rahul", email: "rahul@x.local", phone: "+91 1", active: true, employee_id: "P-1",
  reporting_head: { id: "h1", full_name: "Hema", active: true }, head_active: true,
};

function table(r: PartnershipAdminRow, onChanged = vi.fn()) {
  render(<table><tbody><AdminPartnershipRow row={r} onChanged={onChanged} /></tbody></table>);
  return onChanged;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AdminPartnershipRow (upc-001)", () => {
  it("shows labelled cells and flags a manager with no active head", () => {
    table({ ...row, head_active: false, reporting_head: { ...row.reporting_head, active: false } });
    expect(screen.getByText("No active head")).toBeInTheDocument();
    expect(screen.getByText("P-1").closest("td")).toHaveAttribute("data-label", "Employee ID");
  });

  it("PATCHes name, mobile and the nested profile, keeping the current head", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    const onChanged = table(row);
    fireEvent.click(screen.getByRole("button", { name: "Edit Rahul" }));
    fireEvent.change(screen.getByLabelText("Employee ID (required)"), { target: { value: "P-2" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Saved Rahul."));
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/admin/users/p1");
    expect(JSON.parse(init.body)).toEqual({ full_name: "Rahul", phone: "+91 1", partnership_profile: { employee_id: "P-2", reporting_head_user_id: "h1" } });
  });

  it("keeps the form open with the server's message on error, and Escape cancels", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail: "Employee ID already exists" }, 409)));
    table(row);
    fireEvent.click(screen.getByRole("button", { name: "Edit Rahul" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Employee ID already exists");
    fireEvent.keyDown(screen.getByLabelText("Employee ID (required)"), { key: "Escape" });
    expect(screen.getByRole("button", { name: "Edit Rahul" })).toBeInTheDocument();
  });

  it("deactivates only after an inline confirm", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    const onChanged = table(row);
    fireEvent.click(screen.getByRole("button", { name: "Deactivate Rahul" }));
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Keep active" }));
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Deactivate Rahul" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm deactivate Rahul" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Deactivated Rahul."));
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ active: false });
  });

  it("reactivates an inactive manager", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    const onChanged = table({ ...row, active: false });
    fireEvent.click(screen.getByRole("button", { name: "Reactivate Rahul" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Reactivated Rahul."));
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ active: true });
  });
});
