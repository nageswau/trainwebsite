import { beforeEach, describe, expect, it, vi } from "vitest";

import ChangePasswordForm from "@/components/ChangePasswordForm";
import PublicShell from "@/components/PublicShell";
import { ApiError, serverApi } from "@/lib/api";
import AccountPasswordPage, { metadata } from "@/app/account/password/page";
import { elements, text } from "@/tests/helpers/elementTree";

// Keep the real ApiError (the page tells a 401 from an outage by it); only serverApi is replaced.
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));
// The site header and footer are not what is under test; the page's own decisions are.
vi.mock("@/components/PublicShell", () => ({ default: function PublicShell() { return null; } }));

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
    vi.mocked(serverApi).mockRejectedValue(new ApiError("Not authenticated", 401));
    const tree = await render();
    expect(text(tree.find((el) => el.type === "h1")!)).toBe("Sign in required");
    const links = tree.filter((el) => el.type === "a").map((el) => el.props.href);
    expect(links).toEqual(["/it/login?next=%2Faccount%2Fpassword", "/overseas/login?next=%2Faccount%2Fpassword"]);
    expect(tree.some((el) => el.type === ChangePasswordForm)).toBe(false);
  });

  // QA-002: an outage must not be reported as "you are signed out" -- following that advice leads to a login that fails too.
  it.each([
    ["the API answers 500", () => new ApiError("500 Internal Server Error", 500)],
    ["the API answers 503 with a detail", () => new ApiError("Service unavailable", 503)],
    ["the API cannot be reached at all", () => new TypeError("fetch failed")],
    ["something unexpected is thrown", () => new Error("boom")],
  ])("says the service is unavailable, not \"sign in\", when %s", async (_label, failure) => {
    vi.mocked(serverApi).mockRejectedValue(failure());
    const tree = await render();
    expect(text(tree.find((el) => el.type === "h1")!)).toBe("Temporarily unavailable");
    expect(tree.some((el) => el.type === "p" && text(el).includes("Your password has not been changed"))).toBe(true);
    const retry = tree.find((el) => el.type === "a")!;
    expect(retry.props.href).toBe("/account/password");
    expect(text(retry)).toBe("Try again");
    expect(tree.filter((el) => el.type === "a")).toHaveLength(1);
    expect(tree.some((el) => el.type === ChangePasswordForm)).toBe(false);
  });

  // QA-005: the tab and screen readers announce the page by its title (WCAG 2.4.2); the root layout adds " | EduSphere".
  it("has a page title of its own", () => {
    expect(metadata.title).toBe("Change your password");
  });
});
