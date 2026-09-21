import { isValidElement, type ReactElement, type ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ChangePasswordForm from "@/components/ChangePasswordForm";
import PublicShell from "@/components/PublicShell";
import { serverApi } from "@/lib/api";
import AccountPasswordPage from "@/app/account/password/page";

vi.mock("@/lib/api", () => ({ serverApi: vi.fn() }));
// The site header and footer are not what is under test; the page's own decisions are.
vi.mock("@/components/PublicShell", () => ({ default: function PublicShell() { return null; } }));

type Props = Record<string, unknown> & { children?: ReactNode };

function elements(node: ReactNode, found: ReactElement<Props>[] = []): ReactElement<Props>[] {
  if (Array.isArray(node)) {
    node.forEach((child) => elements(child, found));
  } else if (isValidElement<Props>(node)) {
    found.push(node);
    elements(node.props.children, found);
  }
  return found;
}

function text(node: ReactNode): string {
  if (Array.isArray(node)) return node.map(text).join("");
  if (isValidElement<Props>(node)) return text(node.props.children);
  return typeof node === "string" || typeof node === "number" ? String(node) : "";
}

const user = (overrides: Record<string, unknown> = {}) => ({ id: "u1", email: "asha@example.local", full_name: "Asha Rao", role: "it_student", division: "it", profile: {}, ...overrides });

async function render() {
  return elements(await AccountPasswordPage());
}

// Braces matter: a hook that returns a function is treated by vitest as its cleanup callback, and here that function
// is the mock -- it would be called after the test and, having been set to reject, leak an unhandled rejection.
beforeEach(() => {
  vi.mocked(serverApi).mockReset();
});

describe("/account/password page (ENH-006)", () => {
  it("shows the form for a signed-in student with their email and their division's forgot-password page", async () => {
    vi.mocked(serverApi).mockResolvedValue(user());
    const tree = await render();
    const form = tree.find((el) => el.type === ChangePasswordForm)!;
    expect(form.props.email).toBe("asha@example.local");
    expect(form.props.forgotPasswordHref).toBe("/it/forgot-password");
    expect(tree.find((el) => el.type === PublicShell)!.props.division).toBe("it");
    expect(text(tree.find((el) => el.type === "h1")!)).toBe("Change your password");
    expect(tree.some((el) => el.type === "p" && text(el).includes("Asha Rao (asha@example.local)"))).toBe(true);
    expect(serverApi).toHaveBeenCalledWith("/api/v1/auth/me");
  });

  it("links back to the role's own dashboard so the page is never a dead end", async () => {
    vi.mocked(serverApi).mockResolvedValue(user());
    const back = (await render()).find((el) => el.props.href && text(el).includes("Back to dashboard"))!;
    expect(back.props.href).toBe("/it/student/dashboard");
  });

  it("uses the overseas forgot-password page for an overseas account", async () => {
    vi.mocked(serverApi).mockResolvedValue(user({ role: "overseas_admin", division: "overseas" }));
    const tree = await render();
    expect(tree.find((el) => el.type === ChangePasswordForm)!.props.forgotPasswordHref).toBe("/overseas/forgot-password");
    expect(tree.find((el) => el.type === PublicShell)!.props.division).toBe("overseas");
  });

  it("offers no forgot-password page to the global division, which has none", async () => {
    vi.mocked(serverApi).mockResolvedValue(user({ role: "super_admin", division: "global" }));
    const tree = await render();
    expect(tree.find((el) => el.type === ChangePasswordForm)!.props.forgotPasswordHref).toBeUndefined();
    expect(tree.find((el) => el.type === PublicShell)!.props.division).toBeUndefined();
    expect(tree.find((el) => el.props.href && text(el).includes("Back to dashboard"))!.props.href).toBe("/admin");
  });

  it("falls back to the home page when the role has no dashboard mapping", async () => {
    vi.mocked(serverApi).mockResolvedValue(user({ role: "unmapped_role" }));
    expect((await render()).find((el) => el.props.href && text(el).includes("Back to dashboard"))!.props.href).toBe("/");
  });

  it("asks a signed-out visitor to sign in and returns them to this page afterwards", async () => {
    vi.mocked(serverApi).mockRejectedValue(new Error("Not authenticated"));
    const tree = await render();
    expect(text(tree.find((el) => el.type === "h1")!)).toBe("Sign in required");
    const links = tree.filter((el) => el.type === "a").map((el) => el.props.href);
    expect(links).toEqual(["/it/login?next=%2Faccount%2Fpassword", "/overseas/login?next=%2Faccount%2Fpassword"]);
    expect(tree.some((el) => el.type === ChangePasswordForm)).toBe(false);
  });
});
