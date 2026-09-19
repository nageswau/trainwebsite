import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import WorkflowPanel from "@/components/WorkflowPanel";
import type { User } from "@/lib/types";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }), useSearchParams: () => new URLSearchParams() }));

const itAdmin = { id: "u1", email: "itadmin@example.local", full_name: "IT Admin", role: "it_admin", division: "it" } as unknown as User;
const json = (body: unknown, status: number) => new Response(JSON.stringify(body), { status });

// GET /admin/users (the Manage users list on the same page) then POST /admin/users (the Create user card).
function stubFetch(postResponse: Response) {
  const mock = vi.fn((url: string, init?: RequestInit) => Promise.resolve(init?.method === "POST" ? postResponse : json([], 200)));
  vi.stubGlobal("fetch", mock);
  return mock;
}

async function createUser() {
  render(<WorkflowPanel user={itAdmin} section="users" />);
  await waitFor(() => expect(screen.getByRole("heading", { name: "Create user" })).toBeInTheDocument());
  fireEvent.change(screen.getByLabelText("Full name"), { target: { value: "New Trainer" } });
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "trainer@example.local" } });
  fireEvent.change(screen.getByLabelText("Role"), { target: { value: "trainer" } });
  fireEvent.click(screen.getByRole("button", { name: "Create user" }));
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

// QA-002 / QA-003: the generic Create user card must report what happened to the set-password email --
// exactly like the School and School Staff forms -- and announce it.
describe("WorkflowPanel Create user card (ENH-003)", () => {
  it("says a 72-hour set-password link was emailed, as a polite live status", async () => {
    stubFetch(json({ email: "trainer@example.local", email_status: "sent", expires_at: "2026-09-22T03:28:16Z" }, 201));
    await createUser();
    const outcome = await screen.findByText(/User created\./);
    expect(outcome).toHaveClass("form-message");
    expect(outcome).toHaveTextContent("A set-password link was emailed");
    expect(outcome).toHaveTextContent("72 hours");
    expect(outcome).toHaveAttribute("role", "status");
    expect(outcome).toHaveAttribute("aria-live", "polite");
    expect(outcome.textContent).not.toMatch(/ChangeMe|default password/i);
  });

  it.each(["failed", "not_configured"])("shows an amber warning, not a plain success, when the email status is %s", async (status) => {
    stubFetch(json({ email: "trainer@example.local", email_status: status }, 201));
    await createUser();
    const outcome = await screen.findByText(/User created\./);
    expect(outcome).toHaveClass("form-warning");
    expect(outcome).not.toHaveClass("form-message");
    expect(outcome).toHaveTextContent("The email was not delivered");
    expect(outcome).toHaveTextContent("Re-send");
    expect(outcome).toHaveAttribute("role", "status");
  });

  it("still shows a server rejection as an error, announced assertively", async () => {
    stubFetch(json({ detail: "Email already exists" }, 409));
    await createUser();
    const outcome = await screen.findByText("Email already exists");
    expect(outcome).toHaveClass("form-error");
    expect(outcome).toHaveAttribute("role", "alert");
  });
});
