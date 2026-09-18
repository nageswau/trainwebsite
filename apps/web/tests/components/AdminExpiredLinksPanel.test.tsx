import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminExpiredLinksPanel from "@/components/AdminExpiredLinksPanel";

const rows = [
  { id: "u1", name: "Asha Rao", email: "asha@example.local", role: "academic_team" },
  { id: "u2", name: "Ben Cole", email: "ben@example.local", role: "career_counselor" },
];
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

function stubFetch(handler: (url: string, init?: RequestInit) => Response | Promise<Response>) {
  const mock = vi.fn((url: string, init?: RequestInit) => Promise.resolve(handler(String(url), init)));
  vi.stubGlobal("fetch", mock);
  return mock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AdminExpiredLinksPanel states", () => {
  it("shows a labelled loading state first, then the list with a count", async () => {
    stubFetch(() => json(rows));
    render(<AdminExpiredLinksPanel />);
    expect(screen.getByText("Loading expired links…")).toBeInTheDocument();
    await screen.findByText("Asha Rao");
    expect(screen.getByRole("heading", { name: "Expired set-password links (2)" })).toBeInTheDocument();
    expect(screen.getByText("academic team")).toHaveClass("badge");
    expect(screen.getAllByText("Link expired")).toHaveLength(2);
  });

  it("shows a calm empty state", async () => {
    stubFetch(() => json([]));
    render(<AdminExpiredLinksPanel />);
    expect(await screen.findByText("No expired links.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Expired set-password links" })).toBeInTheDocument();
  });

  it("shows an alert with 'Try again' that recovers", async () => {
    let calls = 0;
    stubFetch(() => (++calls === 1 ? json({}, 500) : json(rows)));
    render(<AdminExpiredLinksPanel />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load expired links.");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Asha Rao")).toBeInTheDocument();
  });

  it("requests only the expired filter and lays out for keyboard users (native buttons, named per person)", async () => {
    const mock = stubFetch(() => json(rows));
    render(<AdminExpiredLinksPanel />);
    await screen.findByText("Asha Rao");
    expect(mock.mock.calls[0][0]).toBe("/api/v1/admin/users?provisioning_status=link_expired");
    expect(screen.getByRole("list", { name: "Accounts with an expired link" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Re-send set-password link to Asha Rao" }).tagName).toBe("BUTTON");
  });
});

describe("AdminExpiredLinksPanel Re-send", () => {
  it("removes the row, announces the outcome and moves focus to the outcome region", async () => {
    const mock = stubFetch((url, init) => (init?.method === "POST" ? json({ id: "u1", email_status: "sent" }, 201) : json(rows)));
    render(<AdminExpiredLinksPanel />);
    await screen.findByText("Asha Rao");
    fireEvent.click(screen.getByRole("button", { name: "Re-send set-password link to Asha Rao" }));

    const status = screen.getByRole("status");
    await waitFor(() => expect(within(status).getByText(/New link created for Asha Rao\./)).toHaveClass("form-message"));
    expect(mock).toHaveBeenCalledWith("/api/v1/admin/users/u1/welcome-links", { method: "POST" });
    expect(screen.queryByText("Asha Rao")).toBeNull();
    expect(screen.getByText("Ben Cole")).toBeInTheDocument();
    await waitFor(() => expect(status).toHaveFocus());
  });

  it("shows an amber warning when the link was created but the email was not delivered", async () => {
    stubFetch((url, init) => (init?.method === "POST" ? json({ email_status: "failed" }, 201) : json(rows)));
    render(<AdminExpiredLinksPanel />);
    await screen.findByText("Asha Rao");
    fireEvent.click(screen.getByRole("button", { name: "Re-send set-password link to Asha Rao" }));
    expect(await screen.findByText(/The email was not delivered/)).toHaveClass("form-warning");
  });

  it("keeps the row on a server error, shows it as an error and returns focus to the button", async () => {
    stubFetch((url, init) => (init?.method === "POST" ? json({ detail: "Reactivate this account before re-sending its link" }, 409) : json(rows)));
    render(<AdminExpiredLinksPanel />);
    await screen.findByText("Asha Rao");
    fireEvent.click(screen.getByRole("button", { name: "Re-send set-password link to Asha Rao" }));
    expect(await screen.findByText("Reactivate this account before re-sending its link")).toHaveClass("form-error");
    const button = screen.getByRole("button", { name: "Re-send set-password link to Asha Rao" });
    expect(button).not.toBeDisabled();
    await waitFor(() => expect(button).toHaveFocus());
  });

  it("survives a network failure without getting stuck busy", async () => {
    let posted = false;
    vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === "POST") { posted = true; return Promise.reject(new TypeError("offline")); }
      return Promise.resolve(json(rows));
    }));
    render(<AdminExpiredLinksPanel />);
    await screen.findByText("Asha Rao");
    fireEvent.click(screen.getByRole("button", { name: "Re-send set-password link to Asha Rao" }));
    expect(await screen.findByText(/Network error/)).toHaveClass("form-error");
    expect(posted).toBe(true);
    expect(screen.getByRole("button", { name: "Re-send set-password link to Asha Rao" })).not.toBeDisabled();
  });
});
