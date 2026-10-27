import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { PermissionCatalogue } from "@/components/PermissionMatrix";
import UserPermissionOverrides from "@/components/UserPermissionOverrides";

// nehn-007 (DEC-SCOPE-297): the "By user" tab -- find a user, see where each permission comes from, set allow/deny overrides with a
// reason and an optional expiry, and see every active override.
const CATALOGUE: PermissionCatalogue = {
  roles: ["super_admin", "hr_team"],
  actions: ["view", "add", "edit", "delete", "download", "approve", "review", "issue", "manage"],
  resources: [
    { key: "payments", label: "Payments", actions: ["view", "add"] },
    { key: "reports.telecaller", label: "Telecaller reports", actions: ["view", "download"] },
  ],
};
const USER_ID = "11111111-1111-1111-1111-111111111111";
const PERSON = { id: USER_ID, full_name: "Hana Rao", email: "hana@example.local", role: "telecaller_manager" };
type Override = { permission: string; effect: string; reason: string; expires_at: string | null; created_at?: string };

function body(overrides: Override[], editable = true) {
  const role = ["reports.telecaller.view", "reports.telecaller.download"];
  const effective = new Set(role);
  for (const o of overrides) if (o.effect === "allow") effective.add(o.permission); else effective.delete(o.permission);
  return { user: PERSON, editable, role_permissions: role, overrides, effective: [...effective].sort() };
}

function api(opts: { overrides?: Override[]; report?: unknown[]; put?: (payload: { overrides: Override[] }) => Response; users?: unknown[]; editable?: boolean; fail?: boolean } = {}) {
  let current = opts.overrides ?? [];
  return vi.fn((url: string, init?: RequestInit) => {
    const json = (data: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(data), { status }));
    if (url.endsWith("/admin/permissions/overrides")) return json(opts.report ?? []);
    if (url.startsWith("/api/v1/admin/users?")) return json(opts.users ?? []);
    if (opts.fail) return json({ detail: "boom" }, 500);
    if (init?.method === "PUT") {
      const payload = JSON.parse(String(init.body));
      if (opts.put) return Promise.resolve(opts.put(payload));
      current = payload.overrides.map((o: Override) => ({ ...o, expires_at: o.expires_at ?? null }));
    }
    return json(body(current, opts.editable ?? true));
  });
}

const select = (name: string) => screen.getByRole("combobox", { name }) as HTMLSelectElement;
const save = () => screen.getByRole("button", { name: "Save overrides" });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("nehn-007 UserPermissionOverrides", () => {
  it("lists every active override with a link to the user", async () => {
    vi.stubGlobal("fetch", api({ report: [{ user_id: USER_ID, full_name: "Hana Rao", email: "hana@example.local", role: "telecaller_manager", permission: "reports.telecaller.download", effect: "deny", reason: "Audit", expires_at: null, created_at: "2026-10-27T00:00:00Z" }] }));
    render(<UserPermissionOverrides catalogue={CATALOGUE} userId={null} />);
    const report = await screen.findByRole("table", { name: "Active overrides" });
    expect(within(report).getByRole("link", { name: "Hana Rao" })).toHaveAttribute("href", `/admin/permissions?tab=user&user=${USER_ID}`);
    expect(within(report).getByText("Telecaller reports: Download")).toBeInTheDocument();
    expect(within(report).getByText("Deny")).toBeInTheDocument();
    expect(within(report).getByText("Audit")).toBeInTheDocument();
  });

  it("says so when no override is active", async () => {
    vi.stubGlobal("fetch", api());
    render(<UserPermissionOverrides catalogue={CATALOGUE} userId={null} />);
    expect(await screen.findByText("No user has an override.")).toBeInTheDocument();
  });

  it("searches users on the server and links each result", async () => {
    // The real /admin/users row carries `name` (not `full_name`) -- QA-01.
    const fetchMock = api({ users: [{ id: USER_ID, name: "Hana Rao", email: "hana@example.local", role: "telecaller_manager" }] });
    vi.stubGlobal("fetch", fetchMock);
    render(<UserPermissionOverrides catalogue={CATALOGUE} userId={null} />);
    fireEvent.change(screen.getByLabelText("Find a user"), { target: { value: "hana" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    const results = await screen.findByRole("list", { name: "Matching users" });
    expect(within(results).getByRole("link", { name: /Hana Rao/ })).toHaveAttribute("href", `/admin/permissions?tab=user&user=${USER_ID}`);
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/admin/users?q=hana", expect.anything());
  });

  it("keeps the newest search when an older one answers last (QA-02)", async () => {
    let releaseOld: (r: Response) => void = () => {};
    const fetchMock = vi.fn((url: string) => {
      if (url.endsWith("/admin/permissions/overrides")) return Promise.resolve(new Response("[]"));
      if (url.endsWith("q=old")) return new Promise<Response>((resolve) => { releaseOld = resolve; });
      return Promise.resolve(new Response(JSON.stringify([{ id: USER_ID, name: "Hana Rao", email: "hana@example.local", role: "hr_team" }])));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<UserPermissionOverrides catalogue={CATALOGUE} userId={null} />);
    const input = screen.getByLabelText("Find a user");
    fireEvent.change(input, { target: { value: "old" } });
    fireEvent.submit(input.closest("form")!);
    fireEvent.change(input, { target: { value: "hana" } });
    fireEvent.submit(input.closest("form")!);
    await screen.findByRole("link", { name: /Hana Rao/ });
    releaseOld(new Response("[]"));
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.getByRole("link", { name: /Hana Rao/ })).toBeInTheDocument();
    expect(screen.queryByText("No user matches.")).toBeNull();
  });

  it("shows where each permission comes from", async () => {
    vi.stubGlobal("fetch", api({ overrides: [{ permission: "payments.view", effect: "allow", reason: "Cover", expires_at: null }] }));
    render(<UserPermissionOverrides catalogue={CATALOGUE} userId={USER_ID} />);
    const table = await screen.findByRole("table", { name: /Permissions for Hana Rao/ });
    const row = (name: string) => within(table).getByRole("row", { name: new RegExp(`^${name}`) });
    expect(within(row("Payments: View")).getByText("Allowed by override")).toBeInTheDocument();
    expect(within(row("Payments: Add")).getAllByRole("cell").at(-1)).toHaveTextContent(/^No$/);
    expect(within(row("Telecaller reports: View")).getByText("Yes, from role")).toBeInTheDocument();
    expect(select("Payments: View override").value).toBe("allow");
  });

  it("saves a deny with its reason and expiry as one replace", async () => {
    const fetchMock = api();
    vi.stubGlobal("fetch", fetchMock);
    render(<UserPermissionOverrides catalogue={CATALOGUE} userId={USER_ID} />);
    await screen.findByRole("table", { name: /Permissions for Hana Rao/ });
    expect(save()).toBeDisabled();
    fireEvent.change(select("Telecaller reports: Download override"), { target: { value: "deny" } });
    fireEvent.change(screen.getByLabelText("Telecaller reports: Download reason"), { target: { value: "Data audit" } });
    fireEvent.change(screen.getByLabelText("Telecaller reports: Download expires"), { target: { value: "2099-12-31" } });
    fireEvent.click(save());
    await screen.findByText("Saved overrides for Hana Rao.");
    const put = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT")!;
    expect(put[0]).toBe(`/api/v1/admin/users/${USER_ID}/permissions`);
    const sent = JSON.parse(String(put[1]!.body)).overrides;
    expect(sent).toHaveLength(1);
    expect(sent[0]).toMatchObject({ permission: "reports.telecaller.download", effect: "deny", reason: "Data audit" });
    expect(new Date(sent[0].expires_at).getFullYear()).toBe(2099);
    expect(within(screen.getByRole("row", { name: /^Telecaller reports: Download/ })).getByText("Denied by override")).toBeInTheDocument();
  });

  it("needs a reason before saving", async () => {
    const fetchMock = api();
    vi.stubGlobal("fetch", fetchMock);
    render(<UserPermissionOverrides catalogue={CATALOGUE} userId={USER_ID} />);
    await screen.findByRole("table", { name: /Permissions for Hana Rao/ });
    fireEvent.change(select("Payments: View override"), { target: { value: "allow" } });
    fireEvent.click(save());
    expect(await screen.findByRole("alert")).toHaveTextContent("Give a reason for each override.");
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PUT")).toBe(false);
  });

  it("offers Reload when someone else changed the overrides", async () => {
    vi.stubGlobal("fetch", api({ put: () => new Response(JSON.stringify({ detail: "These overrides were changed by someone else. Reload and try again." }), { status: 409 }) }));
    render(<UserPermissionOverrides catalogue={CATALOGUE} userId={USER_ID} />);
    await screen.findByRole("table", { name: /Permissions for Hana Rao/ });
    fireEvent.change(select("Payments: View override"), { target: { value: "allow" } });
    fireEvent.change(screen.getByLabelText("Payments: View reason"), { target: { value: "x" } });
    fireEvent.click(save());
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("changed by someone else");
    expect(within(alert).getByRole("button", { name: "Reload" })).toBeInTheDocument();
  });

  it("discards back to the saved overrides", async () => {
    vi.stubGlobal("fetch", api());
    render(<UserPermissionOverrides catalogue={CATALOGUE} userId={USER_ID} />);
    await screen.findByRole("table", { name: /Permissions for Hana Rao/ });
    fireEvent.change(select("Payments: Add override"), { target: { value: "deny" } });
    expect(screen.getByText("1 unsaved change")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Discard" }));
    expect(select("Payments: Add override").value).toBe("");
    expect(save()).toBeDisabled();
  });

  it("shows a super admin read-only", async () => {
    vi.stubGlobal("fetch", api({ editable: false }));
    render(<UserPermissionOverrides catalogue={CATALOGUE} userId={USER_ID} />);
    await screen.findByText("A super admin always holds every permission and cannot have overrides.");
    expect(select("Payments: View override")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Save overrides" })).toBeNull();
  });

  it("offers Try again when the user cannot be loaded", async () => {
    vi.stubGlobal("fetch", api({ fail: true }));
    render(<UserPermissionOverrides catalogue={CATALOGUE} userId={USER_ID} />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("This user's permissions could not be loaded.");
    await waitFor(() => expect(within(alert).getByRole("button", { name: "Try again" })).toBeInTheDocument());
  });
});
