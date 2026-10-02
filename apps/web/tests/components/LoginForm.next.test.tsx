import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import LoginForm from "@/components/LoginForm";

// AGN-008 QA8-07: after sign-in the user lands on `next` (query kept) -- but only a same-origin relative path is followed.
const push = vi.fn();
let search = "";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(search),
}));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  push.mockClear();
});

async function signIn() {
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify({ user: { role: "agent" } }), { status: 200 }))));
  render(<LoginForm division="overseas" />);
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@example.local" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "pw" } });
  fireEvent.submit(screen.getByRole("button", { name: "Sign in securely" }).closest("form")!);
  await waitFor(() => expect(push).toHaveBeenCalledOnce());
  return push.mock.calls[0][0];
}

describe("LoginForm next (QA8-07)", () => {
  it("lands on next with its query string", async () => {
    search = `next=${encodeURIComponent("/overseas/agent/applications?status=enrolled")}`;
    expect(await signIn()).toBe("/overseas/agent/applications?status=enrolled");
  });

  it.each(["//evil.com", "https://evil.com/overseas/agent/dashboard", "/\\evil.com", "/.//evil.com"])("ignores an off-site next %s and goes to the dashboard", async (next) => {
    search = `next=${encodeURIComponent(next)}`;
    expect(await signIn()).toBe("/overseas/agent/dashboard");
  });
});
