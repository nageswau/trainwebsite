import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ProfileForm from "@/components/ProfileForm";

afterEach(cleanup);

beforeEach(() => {
  global.fetch = vi.fn();
});

describe("ProfileForm (ENH-007)", () => {
  it("renders the current full name and phone as initial values", () => {
    render(<ProfileForm fullName="Asha Rao" phone="+91 90000 00000" />);
    expect(screen.getByLabelText("Full name")).toHaveValue("Asha Rao");
    expect(screen.getByLabelText("Phone")).toHaveValue("+91 90000 00000");
  });

  it("renders a blank phone input when phone is null", () => {
    render(<ProfileForm fullName="Asha Rao" phone={null} />);
    expect(screen.getByLabelText("Phone")).toHaveValue("");
  });

  it("PATCHes /api/v1/auth/me with exactly full_name and phone, never profile", async () => {
    vi.mocked(global.fetch).mockResolvedValue(
      new Response(JSON.stringify({ full_name: "New Name", phone: "+91 11111 11111" }), { status: 200 }),
    );
    render(<ProfileForm fullName="Asha Rao" phone="+91 90000 00000" />);
    fireEvent.change(screen.getByLabelText("Full name"), { target: { value: "New Name" } });
    fireEvent.change(screen.getByLabelText("Phone"), { target: { value: "+91 11111 11111" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(global.fetch).toHaveBeenCalled());
    const [url, init] = vi.mocked(global.fetch).mock.calls[0];
    expect(url).toBe("/api/v1/auth/me");
    expect(init?.method).toBe("PATCH");
    const body = JSON.parse(init?.body as string);
    expect(body).toEqual({ full_name: "New Name", phone: "+91 11111 11111" });
    expect(Object.keys(body)).not.toContain("profile");
  });

  it("shows a success message and syncs fields from the response's canonical values after save", async () => {
    vi.mocked(global.fetch).mockResolvedValue(
      new Response(JSON.stringify({ full_name: "Trimmed Name", phone: "+91 11111 11111" }), { status: 200 }),
    );
    render(<ProfileForm fullName="Asha Rao" phone="+91 90000 00000" />);
    fireEvent.change(screen.getByLabelText("Full name"), { target: { value: "  Trimmed Name  " } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByText("Your profile was updated.");
    // Server-trimmed value, not the raw " Trimmed Name " the user typed -- the frontend review
    // finding this closes (spec §6): auth.py:191 strips server-side, and this form must not drift
    // from that canonical value until the next reload.
    expect(screen.getByLabelText("Full name")).toHaveValue("Trimmed Name");
  });
});
