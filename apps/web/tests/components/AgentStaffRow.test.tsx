import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentStaffRow, { type StaffMember } from "@/components/AgentStaffRow";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const active: StaffMember = { id: "s1", code: "ABC-S001", full_name: "Rahul Kumar", email: "rahul@example.local", phone: "+91 1", status: "active", setup: null };

function renderRow(member: StaffMember = active) {
  const onChanged = vi.fn();
  render(<ul><AgentStaffRow member={member} onChanged={onChanged} /></ul>);
  return onChanged;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AgentStaffRow (AGN-002)", () => {
  it.each([
    [{ status: "deactivated" }, "Deactivated"],
    [{ setup: "pending_setup" }, "Set-up pending"],
    [{ setup: "link_expired" }, "Link expired"],
  ] as const)("labels %o as text", (patch, label) => {
    renderRow({ ...active, ...patch } as StaffMember);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it("edits name and phone, Escape cancels and returns focus", async () => {
    const mock = vi.fn().mockResolvedValue(res({ member: { ...active, full_name: "Rahul K" } }));
    vi.stubGlobal("fetch", mock);
    const onChanged = renderRow();
    fireEvent.click(screen.getByRole("button", { name: "Edit Rahul Kumar" }));
    fireEvent.keyDown(screen.getByLabelText("Full name"), { key: "Escape" });
    expect(screen.getByRole("button", { name: "Edit Rahul Kumar" })).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Edit Rahul Kumar" }));
    expect(screen.getByText(/rahul@example\.local/)).toBeInTheDocument(); // email shown, not editable
    expect(screen.queryByLabelText("Email")).toBeNull();
    fireEvent.change(screen.getByLabelText("Full name"), { target: { value: "Rahul K" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await vi.waitFor(() => expect(onChanged).toHaveBeenCalledWith("ABC-S001 updated."));
    expect(mock.mock.calls[0][0]).toBe("/api/v1/workflows/overseas/agent/team/staff/s1");
    expect(JSON.parse(mock.mock.calls[0][1].body)).toEqual({ full_name: "Rahul K", phone: "+91 1" });
  });

  it("deactivates after confirmation; Cancel returns focus", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ member: { ...active, status: "deactivated" } })));
    const onChanged = renderRow();
    fireEvent.click(screen.getByRole("button", { name: "Deactivate Rahul Kumar" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("button", { name: "Deactivate Rahul Kumar" })).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Deactivate Rahul Kumar" }));
    expect(screen.getByRole("button", { name: "Confirm deactivate" })).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Confirm deactivate" }));
    await vi.waitFor(() => expect(onChanged).toHaveBeenCalledWith("ABC-S001 Rahul Kumar deactivated. They have been signed out."));
  });

  it("reactivates and reminds to Reset when set-up never finished", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ member: { ...active, setup: "link_expired" } })));
    const onChanged = renderRow({ ...active, status: "deactivated", setup: "link_expired" });
    fireEvent.click(screen.getByRole("button", { name: "Reactivate Rahul Kumar" }));
    await vi.waitFor(() =>
      expect(onChanged).toHaveBeenCalledWith("ABC-S001 Rahul Kumar reactivated. They have not set a password yet: use Reset to send a new link."),
    );
  });

  it("resets after confirmation and shows a 429 on the row", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail: "A link was just sent; wait 42 seconds before resetting again" }, 429)));
    const onChanged = renderRow();
    fireEvent.click(screen.getByRole("button", { name: "Reset Rahul Kumar" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm reset" }));
    expect(await screen.findByText("A link was just sent; wait 42 seconds before resetting again")).toBeInTheDocument();
    expect(onChanged).not.toHaveBeenCalled();
  });

  it("offers Reset and Deactivate only while active, Reactivate only while deactivated", () => {
    renderRow({ ...active, status: "deactivated" });
    expect(screen.queryByRole("button", { name: /^Reset / })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Deactivate / })).toBeNull();
    expect(screen.getByRole("button", { name: "Reactivate Rahul Kumar" })).toBeInTheDocument();
  });
});
