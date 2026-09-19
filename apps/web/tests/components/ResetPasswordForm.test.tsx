import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ResetPasswordForm from "@/components/ResetPasswordForm";

const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams("token=abc123"),
}));

const json = (body: unknown, status: number) => new Response(JSON.stringify(body), { status });

function stubFetch(response: Response) {
  const mock = vi.fn().mockResolvedValue(response);
  vi.stubGlobal("fetch", mock);
  return mock;
}

async function submit(password = "Brand-New-Pass-1!") {
  fireEvent.change(screen.getByLabelText("New password"), { target: { value: password } });
  fireEvent.click(screen.getByRole("button", { name: "Reset password" }));
}

afterEach(() => {
  cleanup();
  push.mockClear();
  vi.unstubAllGlobals();
});

describe("ResetPasswordForm (ENH-003: also the first-time set-password page)", () => {
  it("posts the token from the link and returns to login on success", async () => {
    const mock = stubFetch(json({ ok: true }, 200));
    render(<ResetPasswordForm division="overseas" />);
    await submit();
    await waitFor(() => expect(push).toHaveBeenCalledWith("/overseas/login"));
    expect(mock).toHaveBeenCalledWith("/api/v1/auth/reset-password", expect.objectContaining({ method: "POST", body: JSON.stringify({ token: "abc123", new_password: "Brand-New-Pass-1!" }) }));
  });

  it("offers a real recovery link when the link is invalid, expired, used or revoked (400)", async () => {
    stubFetch(json({ detail: "Reset token is invalid or expired" }, 400));
    render(<ResetPasswordForm division="overseas" />);
    await submit();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Reset token is invalid or expired");
    expect(alert).toHaveTextContent("ask your administrator to re-send it");
    const link = screen.getByRole("link", { name: "Request a new reset link" });
    expect(link).toHaveAttribute("href", "/overseas/forgot-password");
    expect(push).not.toHaveBeenCalled();
  });

  it("uses the IT portal's forgot-password page for the it division", async () => {
    stubFetch(json({ detail: "Reset token is invalid or expired" }, 400));
    render(<ResetPasswordForm division="it" />);
    await submit();
    expect(await screen.findByRole("link", { name: "Request a new reset link" })).toHaveAttribute("href", "/it/forgot-password");
  });

  it("shows no recovery link for a validation error (422) -- the link is not the problem", async () => {
    stubFetch(json({ detail: "Password must be at most 128 characters" }, 422));
    render(<ResetPasswordForm division="overseas" />);
    await submit("x".repeat(129));
    expect(await screen.findByRole("alert")).toHaveTextContent("Password must be at most 128 characters");
    expect(screen.queryByRole("link", { name: "Request a new reset link" })).toBeNull();
  });

  it("clears the previous recovery hint when the user tries again", async () => {
    const mock = vi.fn().mockResolvedValueOnce(json({ detail: "Reset token is invalid or expired" }, 400)).mockResolvedValueOnce(json({ ok: true }, 200));
    vi.stubGlobal("fetch", mock);
    render(<ResetPasswordForm division="overseas" />);
    await submit();
    await screen.findByRole("link", { name: "Request a new reset link" });
    await submit();
    await waitFor(() => expect(push).toHaveBeenCalledWith("/overseas/login"));
    expect(screen.queryByRole("link", { name: "Request a new reset link" })).toBeNull();
  });

  it("ties the length hint to the password input for screen readers", () => {
    render(<ResetPasswordForm division="overseas" />);
    const input = screen.getByLabelText("New password");
    expect(input).toHaveAttribute("aria-describedby", "reset-password-hint");
    expect(document.getElementById("reset-password-hint")).toHaveTextContent("at least 10 characters");
  });
});

describe("ResetPasswordForm: network failure (QA-007)", () => {
  it("re-enables the button, explains the failure and keeps the typed password when fetch rejects", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    render(<ResetPasswordForm division="overseas" />);
    await submit();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Network error");
    // The server commits before it answers, so a lost response is an UNKNOWN outcome -- never claim "not changed".
    expect(alert).toHaveTextContent("could not confirm whether your password was saved");
    expect(alert.textContent).not.toMatch(/was not changed/i);
    expect(alert).toHaveTextContent("Try signing in");
    const button = screen.getByRole("button", { name: "Reset password" });
    expect(button).toBeEnabled();
    expect(screen.getByLabelText("New password")).toHaveValue("Brand-New-Pass-1!");
    // The link itself is fine -- there is nothing to "request again" for a dropped connection.
    expect(screen.queryByRole("link", { name: "Request a new reset link" })).toBeNull();
    expect(push).not.toHaveBeenCalled();
  });
});
