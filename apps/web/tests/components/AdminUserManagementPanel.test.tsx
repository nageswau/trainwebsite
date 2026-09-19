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

// The status filter is resolved by the server (GET /admin/users?provisioning_status=...), never by slicing a capped list.
function listFor(url: string) {
  const status = new URL(url, "http://x").searchParams.get("provisioning_status");
  return status ? users.filter((u) => u.provisioning_status === status) : users;
}

async function renderPanel() {
  stubFetch((url, init) => (init?.method === "POST" ? json({ id: "p", email_status: "sent" }, 201) : json(listFor(url))));
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
    expect(await screen.findByText("1 account shown")).toHaveAttribute("aria-live", "polite");
    expect(screen.getByText("Eli Expired")).toBeInTheDocument();
    expect(screen.queryByText("Pia Pending")).toBeNull();

    fireEvent.change(screen.getByLabelText("Search by name, email, or role"), { target: { value: "zzz" } });
    expect(screen.getByText("No records match this search.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Search by name, email, or role"), { target: { value: "" } });
    fireEvent.change(filter, { target: { value: "pending_setup" } });
    expect(await screen.findByText("Pia Pending")).toBeInTheDocument();
  });

  it("shows a specific empty message and 'Show all accounts' when the filter matches nobody", async () => {
    stubFetch((url) => json(new URL(url, "http://x").searchParams.get("provisioning_status") ? [] : [users[0]]));
    render(<AdminUserManagementPanel />);
    await screen.findByText("Asha Active");
    fireEvent.change(screen.getByLabelText("Account setup"), { target: { value: "link_expired" } });
    expect(await screen.findByText("No accounts have an expired link.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show all accounts" }));
    expect(await screen.findByText("Asha Active")).toBeInTheDocument();
  });

  // Codex finding 1 (UI): the panel used to filter the newest-500 list it had already fetched, so an older pending or
  // expired account was invisible to the filter and to Re-send. The filter must ask the server for the exact set.
  it("asks the server for the filtered set, so an account outside the unfiltered list is still found", async () => {
    const older = { ...base, id: "o", name: "Olga Older", email: "olga@example.local", role: "career_counselor", active: true, provisioning_status: "link_expired" };
    const mock = vi.fn((url: string) => Promise.resolve(json(new URL(url, "http://x").searchParams.get("provisioning_status") === "link_expired" ? [older] : [users[0]])));
    vi.stubGlobal("fetch", mock);
    render(<AdminUserManagementPanel />);
    await screen.findByText("Asha Active");
    fireEvent.change(screen.getByLabelText("Account setup"), { target: { value: "link_expired" } });
    expect(await screen.findByText("Olga Older")).toBeInTheDocument();
    expect(mock).toHaveBeenCalledWith("/api/v1/admin/users?provisioning_status=link_expired");
    expect(screen.getByRole("button", { name: "Re-send set-password link to Olga Older" })).toBeInTheDocument();
  });

  // Codex finding 3: a successful Re-send turns the row into `pending_setup`; under the "Link expired" filter that
  // used to drop the row -- taking its status message and its focus target with it.
  it("keeps the re-sent row, its message and keyboard focus visible while the Link expired filter is on", async () => {
    await renderPanel();
    fireEvent.change(screen.getByLabelText("Account setup"), { target: { value: "link_expired" } });
    await screen.findByText("1 account shown");
    fireEvent.click(screen.getByRole("button", { name: "Re-send set-password link to Eli Expired" }));
    expect(await screen.findByText(/New link created for Eli Expired\./)).toHaveAttribute("role", "status");
    await waitFor(() => expect(screen.getByRole("button", { name: "Re-send set-password link to Eli Expired" })).toHaveFocus());
    expect(within(screen.getByRole("row", { name: /Eli Expired/ })).getByText("Awaiting setup")).toBeInTheDocument();
  });

  // Codex finding 7: creating an account elsewhere on the page must show up here without a reload.
  it("refetches its list when an account is created elsewhere on the page", async () => {
    let created = false;
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(json(created ? [...users, { ...base, id: "n", name: "Nia New", email: "nia@example.local", role: "trainer", active: true, provisioning_status: "pending_setup" }] : users))));
    render(<AdminUserManagementPanel />);
    await screen.findByText("Pia Pending");
    expect(screen.queryByText("Nia New")).toBeNull();
    created = true;
    window.dispatchEvent(new Event("edusphere:users-changed"));
    expect(await screen.findByText("Nia New")).toBeInTheDocument();
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
