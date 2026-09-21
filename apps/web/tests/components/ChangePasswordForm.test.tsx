import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ChangePasswordForm from "@/components/ChangePasswordForm";

const json = (body: unknown, status: number, headers: Record<string, string> = {}) => new Response(JSON.stringify(body), { status, headers });

function stubFetch(response: Response) {
  const mock = vi.fn().mockResolvedValue(response);
  vi.stubGlobal("fetch", mock);
  return mock;
}

// Passing `{}` renders the form without a forgot-password link (the global division has none); a bare `undefined` argument
// would trigger the default and hide that case.
function renderForm(props: { forgotPasswordHref?: string } = { forgotPasswordHref: "/it/forgot-password" }) {
  return render(<ChangePasswordForm email="asha@example.local" {...props} />);
}

function fill(current = "Sup3r-Secret-Pass!", next = "Brand-New-Pass-1!") {
  fireEvent.change(screen.getByLabelText("Current password"), { target: { value: current } });
  fireEvent.change(screen.getByLabelText("New password"), { target: { value: next } });
}

function submit() {
  fireEvent.click(screen.getByRole("button", { name: "Change password" }));
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ChangePasswordForm (ENH-006)", () => {
  it("posts both passwords, confirms, clears the fields and returns focus to the button on success", async () => {
    const mock = stubFetch(json({ ok: true }, 200));
    renderForm();
    fill();
    submit();
    expect(await screen.findByRole("status")).toHaveTextContent("Your password was changed.");
    expect(mock).toHaveBeenCalledWith(
      "/api/v1/auth/change-password",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ current_password: "Sup3r-Secret-Pass!", new_password: "Brand-New-Pass-1!" }) }),
    );
    expect(screen.getByLabelText("Current password")).toHaveValue("");
    expect(screen.getByLabelText("New password")).toHaveValue("");
    expect(screen.queryByRole("alert")).toBeNull();
    await waitFor(() => expect(screen.getByRole("button", { name: "Change password" })).toHaveFocus());
  });

  it("disables the button and marks the form busy while the request is pending", async () => {
    let release!: (response: Response) => void;
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise<Response>((resolve) => { release = resolve; })));
    renderForm();
    fill();
    submit();
    const button = await screen.findByRole("button", { name: "Changing…" });
    expect(button).toBeDisabled();
    expect(screen.getByRole("form", { name: "Change password" })).toHaveAttribute("aria-busy", "true");
    release(json({ ok: true }, 200));
    expect(await screen.findByRole("status")).toHaveTextContent("Your password was changed.");
    expect(screen.getByRole("button", { name: "Change password" })).toBeEnabled();
    expect(screen.getByRole("form", { name: "Change password" })).toHaveAttribute("aria-busy", "false");
  });

  it("ignores a second submit while one is pending (a repeat after success would burn a rate-limit attempt)", async () => {
    let release!: (response: Response) => void;
    const mock = vi.fn().mockReturnValue(new Promise<Response>((resolve) => { release = resolve; }));
    vi.stubGlobal("fetch", mock);
    renderForm();
    fill();
    const form = screen.getByRole("form", { name: "Change password" });
    fireEvent.submit(form);
    fireEvent.submit(form); // implicit submission / a second event must not slip past the disabled button
    expect(mock).toHaveBeenCalledTimes(1);
    release(json({ ok: true }, 200));
    expect(await screen.findByRole("status")).toBeInTheDocument();
  });

  it("wrong current password (400): generic message, current field flagged, cleared and focused, new password kept, recovery link offered", async () => {
    stubFetch(json({ detail: "Incorrect current password" }, 400));
    renderForm();
    fill();
    submit();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Incorrect current password");
    const current = screen.getByLabelText("Current password");
    expect(current).toHaveAttribute("aria-invalid", "true");
    expect(current).toHaveAttribute("aria-describedby", "change-password-error");
    expect(current).toHaveValue("");
    expect(screen.getByLabelText("New password")).toHaveValue("Brand-New-Pass-1!");
    expect(screen.getByRole("link", { name: "Forgot your current password?" })).toHaveAttribute("href", "/it/forgot-password");
    expect(screen.queryByRole("status")).toBeNull();
    await waitFor(() => expect(current).toHaveFocus());
  });

  it("offers no forgot-password link when the account's division has none", async () => {
    stubFetch(json({ detail: "Incorrect current password" }, 400));
    renderForm({});
    fill();
    submit();
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Forgot your current password?" })).toBeNull();
  });

  it("validation error (422), string or list: message shown, new field flagged and focused", async () => {
    stubFetch(json({ detail: "New password must be different from the current password" }, 422));
    renderForm();
    fill("Same-Password-1!", "Same-Password-1!");
    submit();
    expect(await screen.findByRole("alert")).toHaveTextContent("New password must be different from the current password");
    const next = screen.getByLabelText("New password");
    expect(next).toHaveAttribute("aria-invalid", "true");
    expect(next).toHaveAttribute("aria-describedby", "change-password-hint change-password-error");
    await waitFor(() => expect(next).toHaveFocus());
    expect(screen.queryByRole("link", { name: "Forgot your current password?" })).toBeNull();
    cleanup();
    stubFetch(json({ detail: [{ msg: "String should have at least 10 characters" }] }, 422));
    renderForm();
    fill();
    submit();
    expect(await screen.findByRole("alert")).toHaveTextContent("String should have at least 10 characters");
  });

  it("turns Retry-After into minutes for a rate-limited attempt (429) and flags no field", async () => {
    stubFetch(json({ detail: "Too many incorrect attempts; try again in 720 seconds" }, 429, { "Retry-After": "720" }));
    renderForm();
    fill();
    submit();
    expect(await screen.findByRole("alert")).toHaveTextContent("Too many incorrect attempts. Try again in 12 minutes.");
    expect(screen.getByLabelText("Current password")).not.toHaveAttribute("aria-invalid");
    expect(screen.getByLabelText("New password")).not.toHaveAttribute("aria-invalid");
  });

  it("falls back to the server message for a 429 without a usable Retry-After", async () => {
    stubFetch(json({ detail: "Too many incorrect attempts; try again in 30 seconds" }, 429));
    renderForm();
    fill();
    submit();
    expect(await screen.findByRole("alert")).toHaveTextContent("Too many incorrect attempts; try again in 30 seconds");
  });

  it("sends an expired session (401) back to the sign-in pages and returns here afterwards", async () => {
    stubFetch(json({ detail: "Invalid session" }, 401));
    renderForm();
    fill();
    submit();
    expect(await screen.findByRole("alert")).toHaveTextContent("Your session has expired");
    expect(screen.getByRole("link", { name: "IT Training sign in" })).toHaveAttribute("href", "/it/login?next=%2Faccount%2Fpassword");
    expect(screen.getByRole("link", { name: "Overseas Education sign in" })).toHaveAttribute("href", "/overseas/login?next=%2Faccount%2Fpassword");
  });

  it("says the outcome is unconfirmed when the network fails, and does not claim success", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    renderForm();
    fill();
    submit();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("could not confirm whether your password was changed");
    expect(alert).toHaveTextContent("Sign in with your new password");
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("shows a calm message for an unexpected server error", async () => {
    stubFetch(json({}, 500));
    renderForm();
    fill();
    submit();
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to change password. Try again in a moment.");
  });

  it("clears the previous error when the user tries again", async () => {
    const mock = vi.fn().mockResolvedValueOnce(json({ detail: "Incorrect current password" }, 400)).mockResolvedValueOnce(json({ ok: true }, 200));
    vi.stubGlobal("fetch", mock);
    renderForm();
    fill();
    submit();
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Current password"), { target: { value: "Sup3r-Secret-Pass!" } });
    submit();
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    expect(await screen.findByRole("status")).toHaveTextContent("Your password was changed.");
    expect(screen.getByLabelText("Current password")).not.toHaveAttribute("aria-invalid");
  });

  it("labels the inputs, describes the length rule, and sets the autocomplete tokens", () => {
    renderForm();
    const current = screen.getByLabelText("Current password");
    const next = screen.getByLabelText("New password");
    expect(current).toHaveAttribute("autocomplete", "current-password");
    expect(next).toHaveAttribute("autocomplete", "new-password");
    expect(next).toHaveAttribute("minlength", "10");
    expect(next).toHaveAttribute("maxlength", "128");
    expect(next).toHaveAttribute("aria-describedby", "change-password-hint");
    expect(document.getElementById("change-password-hint")).toHaveTextContent("Use at least 10 characters.");
  });

  it("carries a hidden read-only username for password managers that is never sent", async () => {
    const mock = stubFetch(json({ ok: true }, 200));
    renderForm();
    const username = document.querySelector('input[name="username"]') as HTMLInputElement;
    expect(username).toHaveValue("asha@example.local");
    expect(username).toHaveAttribute("autocomplete", "username");
    expect(username).toHaveAttribute("readonly");
    expect(username).toHaveAttribute("aria-hidden", "true");
    expect(username).toHaveAttribute("tabindex", "-1");
    fill();
    submit();
    await screen.findByRole("status");
    expect(String(mock.mock.calls[0][1].body)).not.toContain("asha@example.local");
  });

  it("shows and hides both passwords with a native checkbox without losing what was typed", () => {
    renderForm();
    fill();
    const toggle = screen.getByRole("checkbox", { name: "Show passwords" });
    expect(screen.getByLabelText("Current password")).toHaveAttribute("type", "password");
    fireEvent.click(toggle);
    expect(screen.getByLabelText("Current password")).toHaveAttribute("type", "text");
    expect(screen.getByLabelText("New password")).toHaveAttribute("type", "text");
    expect(screen.getByLabelText("New password")).toHaveValue("Brand-New-Pass-1!");
    fireEvent.click(toggle);
    expect(screen.getByLabelText("New password")).toHaveAttribute("type", "password");
  });

  it("tells the user other devices stay signed in", () => {
    renderForm();
    expect(screen.getByText(/other devices stay signed in until their sessions expire/i)).toBeInTheDocument();
  });
});
