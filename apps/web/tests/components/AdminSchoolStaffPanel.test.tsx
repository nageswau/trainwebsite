import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminSchoolStaffPanel from "@/components/AdminSchoolStaffPanel";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

const json = (body: unknown, status: number) => new Response(JSON.stringify(body), { status });

// GET /overseas-admin/schools (the portfolio picker) then POST /overseas-admin/school-staff.
function stubFetch(postResponse: Response) {
  const mock = vi.fn((url: string, init?: RequestInit) => Promise.resolve(init?.method === "POST" ? postResponse : json([], 200)));
  vi.stubGlobal("fetch", mock);
  return mock;
}

async function fillAndSubmit() {
  await waitFor(() => expect(screen.getByText(/No partner schools yet/)).toBeInTheDocument());
  fireEvent.change(screen.getByLabelText("Role"), { target: { value: "academic_team" } });
  fireEvent.change(screen.getByLabelText("Full name"), { target: { value: "New Staff" } });
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "staff@example.local" } });
  fireEvent.click(screen.getByRole("button", { name: "Create account" }));
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AdminSchoolStaffPanel (ENH-003: no password is shown, chosen or sent)", () => {
  it("never sends a password field", async () => {
    const mock = stubFetch(json({ email: "staff@example.local", email_status: "sent" }, 201));
    render(<AdminSchoolStaffPanel />);
    await fillAndSubmit();
    await screen.findByRole("status");
    const post = mock.mock.calls.find(([, init]) => init?.method === "POST")!;
    const body = JSON.parse(String(post[1]?.body));
    expect(Object.keys(body).some((key) => key.toLowerCase().includes("password"))).toBe(false);
  });

  it("reports a sent link as a success and never mentions a password", async () => {
    stubFetch(json({ email: "staff@example.local", email_status: "sent" }, 201));
    render(<AdminSchoolStaffPanel />);
    await fillAndSubmit();
    const outcome = await screen.findByText(/Account created for staff@example\.local\./);
    expect(outcome).toHaveClass("form-message");
    expect(outcome).toHaveTextContent("72 hours");
    expect(outcome.textContent).not.toMatch(/ChangeMe|default password/i);
  });

  it("shows an amber warning -- not an error -- when the account exists but the email failed", async () => {
    stubFetch(json({ email: "staff@example.local", email_status: "failed" }, 201));
    render(<AdminSchoolStaffPanel />);
    await fillAndSubmit();
    const outcome = await screen.findByText(/Account created for staff@example\.local\./);
    expect(outcome).toHaveClass("form-warning");
    expect(outcome).toHaveTextContent("could not be sent");
  });

  it("shows a server rejection as an error", async () => {
    stubFetch(json({ detail: "Email already exists" }, 409));
    render(<AdminSchoolStaffPanel />);
    await fillAndSubmit();
    expect(await screen.findByText("Email already exists")).toHaveClass("form-error");
  });
});
