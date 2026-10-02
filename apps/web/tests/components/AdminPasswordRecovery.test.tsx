import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ForgotPasswordForm from "@/components/ForgotPasswordForm";
import LoginForm from "@/components/LoginForm";
import ResetPasswordForm from "@/components/ResetPasswordForm";
import AdminForgotPassword from "@/app/admin/forgot-password/page";
import AdminResetPassword from "@/app/admin/reset-password/page";
import { elements } from "@/tests/helpers/elementTree";

// bdm-001 browser QA-05 (owner, 2026-10-02): BDM managers (division global) recover their password inside the admin portal.
const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams("token=abc123"),
}));

afterEach(() => {
  cleanup();
  push.mockClear();
  vi.unstubAllGlobals();
});

const hrefs = (tree: ReturnType<typeof elements>) => tree.map((el) => el.props.href).filter((h): h is string => typeof h === "string");

describe("admin portal password recovery (QA-05)", () => {
  it("the admin sign-in offers 'Forgot your password?' on the admin portal", () => {
    render(<LoginForm division="global" />);
    expect(screen.getByRole("link", { name: "Forgot your password?" })).toHaveAttribute("href", "/admin/forgot-password");
  });

  it("the division portals keep their own forgot-password links", () => {
    render(<LoginForm division="it" />);
    expect(screen.getByRole("link", { name: "Forgot your password?" })).toHaveAttribute("href", "/it/forgot-password");
  });

  it("/admin/forgot-password links back to the admin sign-in and holds the request form", () => {
    const tree = elements(AdminForgotPassword());
    expect(hrefs(tree)).toContain("/admin/login");
    expect(tree.some((el) => el.type === ForgotPasswordForm)).toBe(true);
  });

  it("/admin/reset-password links back to the admin sign-in and resets as the admin portal", () => {
    const tree = elements(AdminResetPassword());
    expect(hrefs(tree)).toContain("/admin/login");
    expect(hrefs(tree)).not.toContain("/it/login");
    expect(tree.find((el) => el.type === ResetPasswordForm)!.props.division).toBe("admin");
  });

  it("a reset on the admin portal ends at /admin/login", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true, login_portal: null }), { status: 200 })));
    render(<ResetPasswordForm division="admin" />);
    fireEvent.change(screen.getByLabelText("New password"), { target: { value: "Brand-New-Pass-1!" } });
    fireEvent.click(screen.getByRole("button", { name: "Reset password" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/admin/login"));
  });

  it("an expired link on the admin portal offers a new one from the admin portal", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Reset token is invalid or expired" }), { status: 400 })));
    render(<ResetPasswordForm division="admin" />);
    fireEvent.change(screen.getByLabelText("New password"), { target: { value: "Brand-New-Pass-1!" } });
    fireEvent.click(screen.getByRole("button", { name: "Reset password" }));
    expect(await screen.findByRole("link", { name: "Request a new reset link" })).toHaveAttribute("href", "/admin/forgot-password");
  });
});
