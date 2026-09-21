import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import HeaderAuthActions from "@/components/HeaderAuthActions";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }));

const json = (body: unknown, status: number) => new Response(JSON.stringify(body), { status });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("HeaderAuthActions", () => {
  // ENH-006 QA-001: a fifth header button pushed the signed-in header past the viewport (Logout off-screen at 1440 px and
  // narrower). Change password is reached from the portal shell instead (sidebar / mobile menu), so the header keeps its
  // original four actions and must not grow a "Password" link.
  it("shows exactly Dashboard, Privacy and Logout to a signed-in user -- and no Password link", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ role: "it_student" }, 200)));
    render(<HeaderAuthActions loginHref="/it/login" />);
    expect(await screen.findByRole("link", { name: "Dashboard" })).toHaveAttribute("href", "/it/student/dashboard");
    expect(screen.getByRole("link", { name: "Privacy" })).toHaveAttribute("href", "/account/privacy");
    expect(screen.getByRole("button", { name: "Logout" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Password" })).toBeNull();
    expect(screen.getAllByRole("link")).toHaveLength(2);
  });

  it("shows only Login to a signed-out visitor -- no Password link", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ detail: "Not authenticated" }, 401)));
    render(<HeaderAuthActions loginHref="/it/login" />);
    expect(await screen.findByRole("link", { name: "Login" })).toHaveAttribute("href", "/it/login");
    await waitFor(() => expect(screen.queryByRole("link", { name: "Password" })).toBeNull());
  });
});
