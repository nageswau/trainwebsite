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

  // Final review #2: after a successful action focus lands on the row's next logical control, even when that control only
  // appears once the parent has reloaded the row.
  it("moves focus to Reactivate after a deactivation once the row reloads", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ member: { ...active, status: "deactivated" } })));
    const onChanged = vi.fn();
    const { rerender } = render(<ul><AgentStaffRow member={active} onChanged={onChanged} /></ul>);
    fireEvent.click(screen.getByRole("button", { name: "Deactivate Rahul Kumar" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm deactivate" }));
    await vi.waitFor(() => expect(onChanged).toHaveBeenCalled());
    rerender(<ul><AgentStaffRow member={{ ...active, status: "deactivated" }} onChanged={onChanged} /></ul>);
    expect(screen.getByRole("button", { name: "Reactivate Rahul Kumar" })).toHaveFocus();
  });

  it("returns focus to Edit after a save and to Deactivate after a reactivation", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ member: active })));
    const onChanged = vi.fn();
    const { rerender } = render(<ul><AgentStaffRow member={active} onChanged={onChanged} /></ul>);
    fireEvent.click(screen.getByRole("button", { name: "Edit Rahul Kumar" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await vi.waitFor(() => expect(screen.getByRole("button", { name: "Edit Rahul Kumar" })).toHaveFocus());

    rerender(<ul><AgentStaffRow member={{ ...active, status: "deactivated" }} onChanged={onChanged} /></ul>);
    fireEvent.click(screen.getByRole("button", { name: "Reactivate Rahul Kumar" }));
    await vi.waitFor(() => expect(onChanged).toHaveBeenCalledTimes(2));
    rerender(<ul><AgentStaffRow member={active} onChanged={onChanged} /></ul>);
    expect(screen.getByRole("button", { name: "Deactivate Rahul Kumar" })).toHaveFocus();
  });

  // Final review #3: the error region is always mounted (announced reliably) and a cancelled confirmation clears it.
  it("keeps an always-mounted status region for errors and clears it on Cancel", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail: "Already deactivated" }, 409)));
    renderRow();
    const region = screen.getByTestId("staff-row-status-s1");
    expect(region).toHaveAttribute("role", "status");
    expect(region).toBeEmptyDOMElement();
    fireEvent.click(screen.getByRole("button", { name: "Deactivate Rahul Kumar" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm deactivate" }));
    expect(await screen.findByText("Already deactivated")).toBe(region);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(region).toBeEmptyDOMElement();
  });

  // Browser QA-04: Escape closes an inline confirmation and returns focus, like Cancel.
  it.each([["Deactivate", "Confirm deactivate"], ["Reset", "Confirm reset"]])("Escape closes the %s confirmation", (action, confirm) => {
    renderRow();
    fireEvent.click(screen.getByRole("button", { name: `${action} Rahul Kumar` }));
    fireEvent.keyDown(screen.getByRole("button", { name: confirm }), { key: "Escape" });
    expect(screen.queryByRole("button", { name: confirm })).toBeNull();
    expect(screen.getByRole("button", { name: `${action} Rahul Kumar` })).toHaveFocus();
  });

  // Browser QA-05: a dropped connection on an action (nothing typed) must not claim "your entry is kept".
  it("words a dropped connection for an action", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    renderRow();
    fireEvent.click(screen.getByRole("button", { name: "Deactivate Rahul Kumar" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm deactivate" }));
    expect(await screen.findByText("Couldn't reach the server. Check your connection and try again.")).toBeInTheDocument();
  });

  it("keeps the 'entry is kept' wording for a dropped connection while editing", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    renderRow();
    fireEvent.click(screen.getByRole("button", { name: "Edit Rahul Kumar" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText(/your entry is kept/)).toBeInTheDocument();
  });

  // Browser QA-06: a server error without a message says what to do.
  it("tells the Master to try again after a server error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("Internal Server Error", { status: 500 })));
    renderRow();
    fireEvent.click(screen.getByRole("button", { name: "Edit Rahul Kumar" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("The server couldn't complete this. Please try again in a moment.")).toBeInTheDocument();
    expect((screen.getByLabelText("Full name") as HTMLInputElement).value).toBe("Rahul Kumar");
  });

  // Browser QA-08: a phone number never breaks across lines.
  it("keeps the phone number on one line", () => {
    renderRow({ ...active, phone: "+91 98765 43210" });
    expect(screen.getByText("+91 98765 43210")).toHaveStyle({ whiteSpace: "nowrap" });
  });

  it("offers Reset and Deactivate only while active, Reactivate only while deactivated", () => {
    renderRow({ ...active, status: "deactivated" });
    expect(screen.queryByRole("button", { name: /^Reset / })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Deactivate / })).toBeNull();
    expect(screen.getByRole("button", { name: "Reactivate Rahul Kumar" })).toBeInTheDocument();
  });
});
