import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentStaffCreateForm from "@/components/AgentStaffCreateForm";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const member = { id: "s1", code: "ABC-S001", full_name: "Rahul", email: "rahul@example.local", phone: null, status: "active", setup: "pending_setup" };

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function fill() {
  fireEvent.change(screen.getByLabelText("Full name"), { target: { value: "Rahul" } });
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "rahul@example.local" } });
}

describe("AgentStaffCreateForm (AGN-002)", () => {
  it("creates, says the email was sent, clears the form and tells the parent", async () => {
    const mock = vi.fn().mockResolvedValue(res({ member, email_status: "sent" }, 201));
    vi.stubGlobal("fetch", mock);
    const onCreated = vi.fn();
    render(<AgentStaffCreateForm onCreated={onCreated} />);
    fill();
    fireEvent.click(screen.getByRole("button", { name: "Add staff" }));
    expect(await screen.findByText("ABC-S001 created. A set-password link was emailed to rahul@example.local.")).toBeInTheDocument();
    expect(onCreated).toHaveBeenCalledTimes(1);
    expect((screen.getByLabelText("Full name") as HTMLInputElement).value).toBe("");
    expect(JSON.parse(mock.mock.calls[0][1].body)).toEqual({ full_name: "Rahul", email: "rahul@example.local", phone: null });
  });

  it("tells the Master to use Reset when the email was not delivered", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ member, email_status: "not_configured" }, 201)));
    render(<AgentStaffCreateForm onCreated={vi.fn()} />);
    fill();
    fireEvent.click(screen.getByRole("button", { name: "Add staff" }));
    expect(await screen.findByText("ABC-S001 created, but the email was not delivered. Use Reset to send a new link.")).toBeInTheDocument();
  });

  it.each([
    [409, { detail: "Email already exists" }, "Email already exists"],
    [429, { detail: "This agency has created or reset 20 staff logins in the last 24 hours. Try again later." }, "This agency has created or reset 20 staff logins in the last 24 hours. Try again later."],
  ])("shows the server's %s and keeps the entry", async (status, body, text) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res(body, status)));
    const onCreated = vi.fn();
    render(<AgentStaffCreateForm onCreated={onCreated} />);
    fill();
    fireEvent.click(screen.getByRole("button", { name: "Add staff" }));
    expect(await screen.findByText(text)).toBeInTheDocument();
    expect((screen.getByLabelText("Email") as HTMLInputElement).value).toBe("rahul@example.local");
    expect(onCreated).not.toHaveBeenCalled();
  });

  it("reports a dropped network and blocks a double submit", async () => {
    let reject: (e: Error) => void = () => {};
    const mock = vi.fn().mockReturnValue(new Promise((_, r) => { reject = r; }));
    vi.stubGlobal("fetch", mock);
    render(<AgentStaffCreateForm onCreated={vi.fn()} />);
    fill();
    const button = screen.getByRole("button", { name: "Add staff" });
    fireEvent.click(button);
    expect(await screen.findByRole("button", { name: "Adding…" })).toBeDisabled();
    fireEvent.submit(button.closest("form")!);
    expect(mock).toHaveBeenCalledTimes(1);
    reject(new Error("offline"));
    expect(await screen.findByText(/The request did not complete/)).toBeInTheDocument();
  });
});
