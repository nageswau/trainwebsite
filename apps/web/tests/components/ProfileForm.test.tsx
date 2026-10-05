import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ProfileForm from "@/components/ProfileForm";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

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

  it("shows a signed-out banner with both division sign-in links on 401", async () => {
    vi.mocked(global.fetch).mockResolvedValue(new Response(JSON.stringify({ detail: "Not authenticated" }), { status: 401 }));
    render(<ProfileForm fullName="Asha Rao" phone={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByText(/session has expired/);
    expect(screen.getByRole("link", { name: "IT Training sign in" })).toHaveAttribute("href", "/it/login?next=%2Faccount%2Fprofile");
    expect(screen.getByRole("link", { name: "Overseas Education sign in" })).toHaveAttribute("href", "/overseas/login?next=%2Faccount%2Fprofile");
  });

  it("shows an inline field error and focuses full name on 422", async () => {
    vi.mocked(global.fetch).mockResolvedValue(
      new Response(JSON.stringify({ detail: [{ msg: "String should have at least 2 characters" }] }), { status: 422 }),
    );
    render(<ProfileForm fullName="Asha Rao" phone={null} />);
    fireEvent.change(screen.getByLabelText("Full name"), { target: { value: "A" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByText("String should have at least 2 characters");
    expect(screen.getByLabelText("Full name")).toHaveAttribute("aria-invalid", "true");
    await waitFor(() => expect(screen.getByLabelText("Full name")).toHaveFocus());
  });

  it("shows a network-error banner and never claims success", async () => {
    vi.mocked(global.fetch).mockRejectedValue(new TypeError("fetch failed"));
    render(<ProfileForm fullName="Asha Rao" phone={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByText("Network error. Try again.");
    expect(screen.queryByText("Your profile was updated.")).not.toBeInTheDocument();
  });

  it("ignores a second submit while one is pending", async () => {
    let resolveFirst: (value: Response) => void = () => {};
    vi.mocked(global.fetch).mockReturnValue(new Promise((resolve) => { resolveFirst = resolve; }));
    render(<ProfileForm fullName="Asha Rao" phone={null} />);
    const button = screen.getByRole("button", { name: /Save changes|Saving/ });
    fireEvent.click(button);
    fireEvent.click(button);
    resolveFirst(new Response(JSON.stringify({ full_name: "Asha Rao", phone: null }), { status: 200 }));
    await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(1));
  });

  it("refreshes the page once after a successful save (ENH-014: phone validity for the notification section)", async () => {
    refresh.mockClear();
    vi.mocked(global.fetch).mockResolvedValue(new Response(JSON.stringify({ full_name: "Asha Rao", phone: "+91 98765 43210" }), { status: 200 }));
    render(<ProfileForm fullName="Asha Rao" phone={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByText("Your profile was updated.");
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("does not refresh after a failed save", async () => {
    refresh.mockClear();
    vi.mocked(global.fetch).mockResolvedValue(new Response(JSON.stringify({ detail: "bad" }), { status: 422 }));
    render(<ProfileForm fullName="Asha Rao" phone={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByText("bad");
    expect(refresh).not.toHaveBeenCalled();
  });

  // tel-001 QA-01: a 422 about the phone marks and focuses the phone field, not the name.
  it("marks and focuses the phone field when the server's 422 is about the phone (string detail)", async () => {
    vi.mocked(global.fetch).mockResolvedValue(
      new Response(JSON.stringify({ detail: "Phone may contain only digits, spaces and + - ( )" }), { status: 422 }),
    );
    render(<ProfileForm fullName="Asha Rao" phone={null} />);
    fireEvent.change(screen.getByLabelText("Phone"), { target: { value: "abc" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByText("Phone may contain only digits, spaces and + - ( )");
    expect(screen.getByLabelText("Phone")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Phone")).toHaveAttribute("aria-describedby", "profile-error");
    expect(screen.getByLabelText("Full name")).not.toHaveAttribute("aria-invalid");
    await waitFor(() => expect(screen.getByLabelText("Phone")).toHaveFocus());
  });

  it("marks the phone field when a validation-list 422 names the phone", async () => {
    vi.mocked(global.fetch).mockResolvedValue(
      new Response(JSON.stringify({ detail: [{ loc: ["body", "phone"], msg: "String should have at most 40 characters" }] }), { status: 422 }),
    );
    render(<ProfileForm fullName="Asha Rao" phone={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByText("String should have at most 40 characters");
    expect(screen.getByLabelText("Phone")).toHaveAttribute("aria-invalid", "true");
    await waitFor(() => expect(screen.getByLabelText("Phone")).toHaveFocus());
  });

  // tel-001 QA-02 (TL8): a telecaller's name is read-only here, but it is still submitted unchanged so the phone can be saved.
  it("shows the name read-only with a hint when nameLocked, and still submits it unchanged", async () => {
    vi.mocked(global.fetch).mockResolvedValue(new Response(JSON.stringify({ full_name: "Asha Rao", phone: "+91 1" }), { status: 200 }));
    render(<ProfileForm fullName="Asha Rao" phone={null} nameLocked />);
    const name = screen.getByLabelText("Full name");
    expect(name).toHaveAttribute("readonly");
    expect(name).toHaveAccessibleDescription("Your administrator manages your name.");
    fireEvent.change(screen.getByLabelText("Phone"), { target: { value: "+91 1" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(global.fetch).toHaveBeenCalled());
    expect(JSON.parse(vi.mocked(global.fetch).mock.calls[0][1]?.body as string)).toEqual({ full_name: "Asha Rao", phone: "+91 1" });
  });

  it("keeps the name editable by default", () => {
    render(<ProfileForm fullName="Asha Rao" phone={null} />);
    expect(screen.getByLabelText("Full name")).not.toHaveAttribute("readonly");
  });
});
