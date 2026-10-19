import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CounselorWalkInStudentRow, { type WalkInStudent } from "@/components/CounselorWalkInStudentRow";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const pending: WalkInStudent = { id: "s1", full_name: "Meena Walkin", email: "meena@exmaple.local", phone: "+91 90000 11111", student_code: "9CD114AA", setup: "pending_setup" };

function renderRow(student: WalkInStudent = pending) {
  const onChanged = vi.fn();
  render(<ul><CounselorWalkInStudentRow student={student} onChanged={onChanged} /></ul>);
  return onChanged;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("CounselorWalkInStudentRow (csc-003)", () => {
  it("shows the student with Edit and Resend link while set-up is pending", () => {
    renderRow();
    expect(screen.getByText("Meena Walkin")).toBeInTheDocument();
    expect(screen.getByText("Set-up pending")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit Meena Walkin" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Resend link to Meena Walkin" })).toBeInTheDocument();
  });

  it("offers the actions on an expired link too, but none once the student is active", () => {
    renderRow({ ...pending, setup: "link_expired" });
    expect(screen.getByText("Link expired")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Resend link to Meena Walkin" })).toBeInTheDocument();
    cleanup();
    renderRow({ ...pending, setup: null });
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Edit|Resend/ })).toBeNull();
  });

  it("resends the link and announces it", async () => {
    const mock = vi.fn().mockResolvedValue(res({ student: pending, email_status: "sent" }, 201));
    vi.stubGlobal("fetch", mock);
    const onChanged = renderRow();
    fireEvent.click(screen.getByRole("button", { name: "Resend link to Meena Walkin" }));
    await vi.waitFor(() => expect(onChanged).toHaveBeenCalledWith("A new set-password link was emailed to meena@exmaple.local."));
    expect(mock.mock.calls[0][0]).toBe("/api/v1/counselor/students/s1/welcome-links");
    expect(mock.mock.calls[0][1].method).toBe("POST");
  });

  it("shows a cooldown refusal in the row", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail: "A link was just sent; wait 42 seconds before re-sending" }, 429)));
    const onChanged = renderRow();
    fireEvent.click(screen.getByRole("button", { name: "Resend link to Meena Walkin" }));
    expect(await screen.findByText("A link was just sent; wait 42 seconds before re-sending")).toBeInTheDocument();
    expect(onChanged).not.toHaveBeenCalled();
  });

  it("edits the details, sends only what changed, and says when a new link went to a new address", async () => {
    const mock = vi.fn().mockResolvedValue(res({ student: { ...pending, email: "meena@example.local" }, email_status: "sent" }));
    vi.stubGlobal("fetch", mock);
    const onChanged = renderRow();
    fireEvent.click(screen.getByRole("button", { name: "Edit Meena Walkin" }));
    const form = screen.getByRole("form", { name: "Edit Meena Walkin" });
    expect(within(form).getByText("Changing the email sends a new link to the new address; the old link stops working.")).toBeInTheDocument();
    fireEvent.change(within(form).getByLabelText("Email"), { target: { value: "meena@example.local" } });
    fireEvent.change(within(form).getByLabelText("Phone (optional)"), { target: { value: " " } });
    fireEvent.click(within(form).getByRole("button", { name: "Save" }));
    await vi.waitFor(() => expect(onChanged).toHaveBeenCalledWith("Meena Walkin updated. A new set-password link was emailed to meena@example.local."));
    const [url, init] = mock.mock.calls[0];
    expect(url).toBe("/api/v1/counselor/students/s1");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toEqual({ email: "meena@example.local", phone: null });
  });

  it("announces a plain update when no new link was sent", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ student: { ...pending, full_name: "Meena W" } })));
    const onChanged = renderRow();
    fireEvent.click(screen.getByRole("button", { name: "Edit Meena Walkin" }));
    const form = screen.getByRole("form", { name: "Edit Meena Walkin" });
    fireEvent.change(within(form).getByLabelText("Full name"), { target: { value: "Meena W" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save" }));
    await vi.waitFor(() => expect(onChanged).toHaveBeenCalledWith("Meena W updated."));
  });

  it("keeps the entry and shows the reason when the email is taken", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail: "Email already exists" }, 409)));
    const onChanged = renderRow();
    fireEvent.click(screen.getByRole("button", { name: "Edit Meena Walkin" }));
    const form = screen.getByRole("form", { name: "Edit Meena Walkin" });
    fireEvent.change(within(form).getByLabelText("Email"), { target: { value: "taken@example.local" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Email already exists")).toBeInTheDocument();
    expect((within(form).getByLabelText("Email") as HTMLInputElement).value).toBe("taken@example.local");
    expect(onChanged).not.toHaveBeenCalled();
  });

  it("cancels with Cancel or Escape and returns focus to Edit", () => {
    vi.stubGlobal("fetch", vi.fn());
    renderRow();
    fireEvent.click(screen.getByRole("button", { name: "Edit Meena Walkin" }));
    fireEvent.keyDown(screen.getByRole("form", { name: "Edit Meena Walkin" }), { key: "Escape" });
    expect(screen.queryByRole("form", { name: "Edit Meena Walkin" })).toBeNull();
    expect(screen.getByRole("button", { name: "Edit Meena Walkin" })).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Edit Meena Walkin" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("form", { name: "Edit Meena Walkin" })).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("an unchanged Save sends nothing and just closes", () => {
    vi.stubGlobal("fetch", vi.fn());
    const onChanged = renderRow();
    fireEvent.click(screen.getByRole("button", { name: "Edit Meena Walkin" }));
    fireEvent.click(within(screen.getByRole("form", { name: "Edit Meena Walkin" })).getByRole("button", { name: "Save" }));
    expect(screen.queryByRole("form", { name: "Edit Meena Walkin" })).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
    expect(onChanged).not.toHaveBeenCalled();
  });
});
