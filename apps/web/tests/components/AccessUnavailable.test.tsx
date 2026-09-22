import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { accessUnavailable } from "@/components/AccessUnavailable";
import { ApiError, serverApi } from "@/lib/api";

// Browser QA-14 (ENH-011): the "Access unavailable" card offered "Return to login" even to someone who is signed in but lacks the
// role. Signed out keeps the login link; signed in gets their own dashboard instead.
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, serverApi: vi.fn() };
});
const me = vi.mocked(serverApi);

beforeEach(() => me.mockReset());
afterEach(cleanup);

describe("AccessUnavailable", () => {
  it("offers login when the session is missing, without asking the API who the user is", async () => {
    render(await accessUnavailable(new ApiError("Not authenticated", 401)));
    expect(screen.getByRole("heading", { level: 1, name: "Access unavailable" })).toBeTruthy();
    expect(screen.getByText("Not authenticated")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Return to login" }).getAttribute("href")).toBe("/overseas/login");
    expect(me).not.toHaveBeenCalled();
  });

  it("sends a signed-in user without the role to their own dashboard, not to login", async () => {
    me.mockResolvedValue({ role: "academic_team" });
    render(await accessUnavailable(new ApiError("Career Counselor role required", 403)));
    expect(screen.getByText("Career Counselor role required")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Go to your dashboard" }).getAttribute("href")).toBe("/school/academic-team/dashboard");
    expect(screen.queryByRole("link", { name: "Return to login" })).toBeNull();
    expect(me).toHaveBeenCalledWith("/api/v1/auth/me");
  });

  it("falls back to login when who the user is cannot be read, and to the home page for a role without a dashboard", async () => {
    me.mockRejectedValue(new ApiError("Not authenticated", 401));
    render(await accessUnavailable(new ApiError("School role required", 403)));
    expect(screen.getByRole("link", { name: "Return to login" })).toBeTruthy();
    cleanup();
    me.mockResolvedValue({ role: "someone_new" });
    render(await accessUnavailable(new Error("boom")));
    expect(screen.getByRole("link", { name: "Go to your dashboard" }).getAttribute("href")).toBe("/");
  });

  it("uses the division's own login page when given one", async () => {
    render(await accessUnavailable(new ApiError("Not authenticated", 401), "/it/login"));
    expect(screen.getByRole("link", { name: "Return to login" }).getAttribute("href")).toBe("/it/login");
  });

  it("shows a generic reason for something that is not an Error", async () => {
    me.mockResolvedValue({ role: "school_parent" });
    render(await accessUnavailable({ reason: "not an Error" }));
    expect(screen.getByText("Unable to load this workspace")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Go to your dashboard" }).getAttribute("href")).toBe("/school/parent/dashboard");
  });
});
