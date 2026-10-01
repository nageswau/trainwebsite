import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SignOutButton from "@/components/SignOutButton";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("SignOutButton (AGN-001 browser QA-02)", () => {
  it("ends the session and goes to the given login page", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    const assign = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("location", { ...window.location, assign });
    render(<SignOutButton redirectTo="/overseas/login" />);
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    await waitFor(() => expect(assign).toHaveBeenCalledWith("/overseas/login"));
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/auth/logout", { method: "POST" });
  });

  it("still leaves for the login page when the network call fails", async () => {
    const assign = vi.fn();
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    vi.stubGlobal("location", { ...window.location, assign });
    render(<SignOutButton redirectTo="/overseas/login" />);
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    await waitFor(() => expect(assign).toHaveBeenCalledWith("/overseas/login"));
  });
});
