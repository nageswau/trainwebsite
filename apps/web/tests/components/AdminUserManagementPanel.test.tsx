import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminUserManagementPanel from "@/components/AdminUserManagementPanel";

const { refresh } = vi.hoisted(() => ({ refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const base = { division: "overseas", phone: null, profile: {} };
const users = [
  { ...base, id: "a", name: "Asha Active", email: "asha@example.local", role: "counselor", active: true, provisioning_status: "active" },
  { ...base, id: "p", name: "Pia Pending", email: "pia@example.local", role: "academic_team", active: true, provisioning_status: "pending_setup" },
  { ...base, id: "e", name: "Eli Expired", email: "eli@example.local", role: "career_counselor", active: true, provisioning_status: "link_expired" },
  { ...base, id: "d", name: "Dan Deactivated", email: "dan@example.local", role: "counselor", active: false, provisioning_status: "pending_setup" },
];

function stubFetch(handler: (url: string, init?: RequestInit) => Response | Promise<Response>) {
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => Promise.resolve(handler(String(url), init))));
}
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

afterEach(() => {
  cleanup();
  refresh.mockReset();
  vi.unstubAllGlobals();
});

async function renderPanel() {
  stubFetch((url, init) => (init?.method === "POST" ? json({ id: "p", email_status: "sent" }, 201) : json(users)));
  render(<AdminUserManagementPanel />);
  await screen.findByText("Pia Pending");
}

describe("AdminUserManagementPanel setup status", () => {
  it("shows a text pill only for accounts that have not set a password", async () => {
    await renderPanel();
    const pia = screen.getByRole("row", { name: /Pia Pending/ });
    expect(within(pia).getByText("Awaiting setup")).toHaveClass("status", "pending");
    expect(within(screen.getByRole("row", { name: /Eli Expired/ })).getByText("Link expired")).toHaveClass("status", "error");
    expect(within(screen.getByRole("row", { name: /Asha Active/ })).queryByText(/Awaiting setup|Link expired/)).toBeNull();
  });

  it("offers Re-send only for active accounts that are pending or expired, with a per-person accessible name", async () => {
    await renderPanel();
    expect(screen.getByRole("button", { name: "Re-send set-password link to Pia Pending" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Re-send set-password link to Eli Expired" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Re-send set-password link to Asha Active/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Re-send set-password link to Dan Deactivated/ })).toBeNull();
  });
});

describe("AdminUserManagementPanel setup filter", () => {
  it("narrows the list, announces the count, and offers a way back when nothing matches", async () => {
    await renderPanel();
    const filter = screen.getByLabelText("Account setup");
    fireEvent.change(filter, { target: { value: "link_expired" } });
    expect(screen.getByText("Eli Expired")).toBeInTheDocument();
    expect(screen.queryByText("Pia Pending")).toBeNull();
    expect(screen.getByText("1 account shown")).toHaveAttribute("aria-live", "polite");

    fireEvent.change(screen.getByLabelText("Search by name, email, or role"), { target: { value: "zzz" } });
    expect(screen.getByText("No records match this search.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Search by name, email, or role"), { target: { value: "" } });
    fireEvent.change(filter, { target: { value: "pending_setup" } });
    expect(screen.getByText("Pia Pending")).toBeInTheDocument();
  });

  it("shows a specific empty message and 'Show all accounts' when the filter matches nobody", async () => {
    stubFetch(() => json([users[0]]));
    render(<AdminUserManagementPanel />);
    await screen.findByText("Asha Active");
    fireEvent.change(screen.getByLabelText("Account setup"), { target: { value: "link_expired" } });
    expect(screen.getByText("No accounts have an expired link.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show all accounts" }));
    expect(screen.getByText("Asha Active")).toBeInTheDocument();
  });

  it("makes the scrollable table keyboard-reachable", async () => {
    await renderPanel();
    const region = screen.getByRole("region", { name: "Users" });
    expect(region).toHaveAttribute("tabindex", "0");
  });
});

describe("AdminUserManagementPanel Re-send", () => {
  it("re-sends, reports the outcome in a live region, marks the row pending and returns focus to the button", async () => {
    await renderPanel();
    const button = screen.getByRole("button", { name: "Re-send set-password link to Eli Expired" });
    fireEvent.click(button);
    const outcome = await screen.findByText(/New link created for Eli Expired\./);
    expect(outcome).toHaveClass("form-message");
    expect(outcome).toHaveAttribute("aria-live", "polite");
    expect(within(screen.getByRole("row", { name: /Eli Expired/ })).getByText("Awaiting setup")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Re-send set-password link to Eli Expired" })).toHaveFocus());
  });

  // QA-004: in the browser a successful Re-send left focus on <body>. The old test's refresh() was a no-op, so it could
  // never see it. This one behaves like Next: whatever a server refresh re-renders drops focus, a moment AFTER the
  // refocus frame has run. Re-send already updates the row locally, so it must not depend on a refresh at all.
  it("keeps keyboard focus on the button after a successful re-send even if a server refresh would drop it", async () => {
    refresh.mockImplementation(() => {
      setTimeout(() => (document.activeElement as HTMLElement | null)?.blur(), 50);
    });
    await renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Re-send set-password link to Eli Expired" }));
    await screen.findByText(/New link created for Eli Expired\./);
    await new Promise((resolve) => setTimeout(resolve, 200));
    expect(screen.getByRole("button", { name: "Re-send set-password link to Eli Expired" })).toHaveFocus();
  });

  it("shows an amber warning, not an error, when the link was created but the email was not sent", async () => {
    stubFetch((url, init) => (init?.method === "POST" ? json({ email_status: "not_configured" }, 201) : json(users)));
    render(<AdminUserManagementPanel />);
    await screen.findByText("Pia Pending");
    fireEvent.click(screen.getByRole("button", { name: "Re-send set-password link to Pia Pending" }));
    expect(await screen.findByText(/The email was not delivered/)).toHaveClass("form-warning");
  });

  it("shows the server's error, keeps the row and re-enables the button", async () => {
    stubFetch((url, init) => (init?.method === "POST" ? json({ detail: "This account has no pending invitation (its password is already set)" }, 409) : json(users)));
    render(<AdminUserManagementPanel />);
    await screen.findByText("Pia Pending");
    fireEvent.click(screen.getByRole("button", { name: "Re-send set-password link to Pia Pending" }));
    expect(await screen.findByText(/no pending invitation/)).toHaveClass("form-error");
    expect(screen.getByRole("button", { name: "Re-send set-password link to Pia Pending" })).not.toBeDisabled();
  });
});
