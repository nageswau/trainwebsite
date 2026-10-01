import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import RegisterForm from "@/components/RegisterForm";

const { push, refresh } = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh }) }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

function fill() {
  fireEvent.change(screen.getByLabelText("Full name"), { target: { value: "Asha Rao" } });
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "asha@example.local" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "Sup3r-Secret-Pass!" } });
}

describe("RegisterForm (AGN-001)", () => {
  it("shows the agency name field only for an education agent", () => {
    render(<RegisterForm division="overseas" />);
    expect(screen.queryByLabelText("Agency name (optional)")).toBeNull();
    fireEvent.change(screen.getByLabelText("Account type"), { target: { value: "agent" } });
    expect(screen.getByLabelText("Agency name (optional)")).toHaveAttribute("maxLength", "160");
  });

  it("sends agency_name for an agent", async () => {
    const mock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ user: { role: "agent" } }), { status: 201 }));
    vi.stubGlobal("fetch", mock);
    render(<RegisterForm division="overseas" />);
    fill();
    fireEvent.change(screen.getByLabelText("Account type"), { target: { value: "agent" } });
    fireEvent.change(screen.getByLabelText("Agency name (optional)"), { target: { value: "ABC Overseas" } });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/overseas/agent/dashboard"));
    expect(JSON.parse(mock.mock.calls[0][1].body)).toMatchObject({ account_type: "agent", agency_name: "ABC Overseas" });
  });

  it("sends no agency_name for a student", async () => {
    const mock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ user: { role: "overseas_student" } }), { status: 201 }));
    vi.stubGlobal("fetch", mock);
    render(<RegisterForm division="overseas" />);
    fill();
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() => expect(push).toHaveBeenCalled());
    expect(JSON.parse(mock.mock.calls[0][1].body)).not.toHaveProperty("agency_name");
  });
});
