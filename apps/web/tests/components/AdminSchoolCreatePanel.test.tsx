import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminSchoolCreatePanel from "@/components/AdminSchoolCreatePanel";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

const json = (body: unknown, status: number) => new Response(JSON.stringify(body), { status });

function stubFetch(response: Response) {
  const mock = vi.fn().mockResolvedValue(response);
  vi.stubGlobal("fetch", mock);
  return mock;
}

function fillAndSubmit() {
  fireEvent.change(screen.getByLabelText("School name"), { target: { value: "Test School" } });
  fireEvent.change(screen.getByLabelText("Coordinator full name"), { target: { value: "Coord One" } });
  fireEvent.change(screen.getByLabelText("Coordinator email"), { target: { value: "coord@example.local" } });
  fireEvent.click(screen.getByRole("button", { name: "Create school + seed Coordinator" }));
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AdminSchoolCreatePanel (ENH-003: no password is shown, chosen or sent)", () => {
  it("never sends a password field", async () => {
    const mock = stubFetch(json({ coordinator_email: "coord@example.local", email_status: "sent" }, 201));
    render(<AdminSchoolCreatePanel />);
    fillAndSubmit();
    await screen.findByRole("status");
    const body = JSON.parse(mock.mock.calls[0][1].body);
    expect(Object.keys(body).some((key) => key.toLowerCase().includes("password"))).toBe(false);
  });

  it("reports a sent link as a success, keeps the wording the e2e specs match, and never mentions a password", async () => {
    stubFetch(json({ coordinator_email: "coord@example.local", email_status: "sent" }, 201));
    render(<AdminSchoolCreatePanel />);
    fillAndSubmit();
    const outcome = await screen.findByText(/School created\./);
    expect(outcome).toHaveClass("form-message");
    expect(outcome).toHaveAttribute("aria-live", "polite");
    expect(outcome).toHaveTextContent("coord@example.local");
    expect(outcome).toHaveTextContent("72 hours");
    expect(outcome.textContent).not.toMatch(/ChangeMe|default password/i);
  });

  it("shows an amber warning -- not an error -- when the school was created but the email was not delivered", async () => {
    stubFetch(json({ coordinator_email: "coord@example.local", email_status: "not_configured" }, 201));
    render(<AdminSchoolCreatePanel />);
    fillAndSubmit();
    const outcome = await screen.findByText(/School created\./);
    expect(outcome).toHaveClass("form-warning");
    expect(outcome).not.toHaveClass("form-error");
    expect(outcome).toHaveTextContent("not configured");
    expect(outcome).toHaveTextContent("Re-send");
  });

  it("shows a server rejection as an error", async () => {
    stubFetch(json({ detail: "A valid email address is required" }, 422));
    render(<AdminSchoolCreatePanel />);
    fillAndSubmit();
    const outcome = await screen.findByText("A valid email address is required");
    expect(outcome).toHaveClass("form-error");
  });

  it("submits the new profile fields alongside the existing ones", async () => {
    const mock = stubFetch(json({ coordinator_email: "coord@example.local", email_status: "sent", school_code: "ABCD1234" }, 201));
    render(<AdminSchoolCreatePanel />);
    fireEvent.change(screen.getByLabelText("School name"), { target: { value: "Test School" } });
    fireEvent.change(screen.getByLabelText("Coordinator full name"), { target: { value: "Coord One" } });
    fireEvent.change(screen.getByLabelText("Coordinator email"), { target: { value: "coord@example.local" } });
    fireEvent.change(screen.getByLabelText("Branch"), { target: { value: "North Campus" } });
    fireEvent.change(screen.getByLabelText("Board"), { target: { value: "CBSE" } });
    fireEvent.click(screen.getByRole("button", { name: "Create school + seed Coordinator" }));
    await screen.findByRole("status");
    const body = JSON.parse(mock.mock.calls[0][1].body);
    expect(body.branch).toBe("North Campus");
    expect(body.board).toBe("CBSE");
  });
});

describe("AdminSchoolCreatePanel: network failure (QA-008)", () => {
  it("re-enables the button, explains the failure and keeps the typed values when the POST rejects", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    render(<AdminSchoolCreatePanel />);
    fillAndSubmit();
    const outcome = await screen.findByText(/Network error/);
    expect(outcome).toHaveClass("form-error");
    expect(outcome).toHaveTextContent("not known whether the school was created");
    expect(screen.getByRole("button", { name: "Create school + seed Coordinator" })).toBeEnabled();
    expect(screen.getByLabelText("School name")).toHaveValue("Test School");
  });
});
