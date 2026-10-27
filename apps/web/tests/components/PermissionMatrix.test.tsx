import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import PermissionMatrix, { type PermissionCatalogue } from "@/components/PermissionMatrix";

// nehn-006 (DEC-SCOPE-295): the Super Admin's role x resource x action matrix over nehn-005's endpoints.
const CATALOGUE: PermissionCatalogue = {
  roles: ["super_admin", "it_admin", "coordinator"],
  actions: ["view", "add", "edit", "delete", "download", "approve", "review", "issue", "manage"],
  resources: [
    { key: "payments", label: "Payments", actions: ["view", "add"] },
    { key: "reports.telecaller", label: "Telecaller reports", actions: ["view", "download"] },
  ],
};

type Grants = Record<string, string[]>;

function api(grants: Grants, put?: (role: string, keys: string[]) => Response) {
  return vi.fn((url: string, init?: RequestInit) => {
    const role = decodeURIComponent(url.split("/roles/")[1].split("/")[0]);
    if (init?.method === "PUT") {
      const keys = JSON.parse(String(init.body)).permissions as string[];
      if (put) return Promise.resolve(put(role, keys));
      grants[role] = [...keys].sort();
    }
    return Promise.resolve(new Response(JSON.stringify({ role, permissions: grants[role] ?? [], editable: role !== "super_admin" }), { status: 200 }));
  });
}

const cell = (name: string) => screen.getByRole("checkbox", { name }) as HTMLInputElement;
const save = () => screen.getByRole("button", { name: "Save changes" });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("nehn-006 PermissionMatrix", () => {
  it("shows every resource x the nine actions; a non-applicable cell has no checkbox", async () => {
    vi.stubGlobal("fetch", api({ it_admin: ["payments.view"] }));
    render(<PermissionMatrix catalogue={CATALOGUE} />);
    await waitFor(() => expect(cell("Payments: View")).toBeChecked());
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Resource", "View", "Add", "Edit", "Delete", "Download", "Approve", "Review", "Issue", "Manage"]);
    expect(within(table).getAllByRole("rowheader").map((h) => h.textContent)).toEqual(["Payments", "Telecaller reports"]);
    expect(within(table).getAllByRole("checkbox")).toHaveLength(4);
    expect(cell("Payments: Add")).not.toBeChecked();
    expect(within(table).getAllByText("Not applicable")).toHaveLength(14);
    // The matrix scrolls in its own labelled region, never the page.
    expect(screen.getByRole("region", { name: "Permissions for IT Administrator" })).toHaveClass("table-scroll");
  });

  it("starts on the first editable role and offers every role", async () => {
    vi.stubGlobal("fetch", api({}));
    render(<PermissionMatrix catalogue={CATALOGUE} />);
    const picker = screen.getByLabelText("Role") as HTMLSelectElement;
    expect(picker.value).toBe("it_admin");
    expect(within(picker).getAllByRole("option").map((o) => o.textContent)).toEqual(["Super Administrator", "IT Administrator", "Coordinator"]);
    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/v1/admin/roles/it_admin/permissions", expect.objectContaining({ cache: "no-store" })));
  });

  it("saves the toggled set with one PUT and reports the change count", async () => {
    const grants: Grants = { it_admin: ["payments.view", "reports.telecaller.view"] };
    const fetchMock = api(grants);
    vi.stubGlobal("fetch", fetchMock);
    render(<PermissionMatrix catalogue={CATALOGUE} />);
    await waitFor(() => expect(cell("Payments: View")).toBeChecked());
    expect(save()).toBeDisabled();
    fireEvent.click(cell("Payments: View"));
    fireEvent.click(cell("Telecaller reports: Download"));
    expect(screen.getByText("2 unsaved changes")).toBeInTheDocument();
    fireEvent.click(save());
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Saved IT Administrator: 2 changes."));
    const put = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT");
    expect(put?.[0]).toBe("/api/v1/admin/roles/it_admin/permissions");
    expect(JSON.parse(String(put?.[1]?.body))).toEqual({ permissions: ["reports.telecaller.download", "reports.telecaller.view"] });
    expect(cell("Payments: View")).not.toBeChecked();
    expect(save()).toBeDisabled();
  });

  it("Discard restores the saved set", async () => {
    vi.stubGlobal("fetch", api({ it_admin: ["payments.view"] }));
    render(<PermissionMatrix catalogue={CATALOGUE} />);
    await waitFor(() => expect(cell("Payments: View")).toBeChecked());
    fireEvent.click(cell("Payments: View"));
    fireEvent.click(screen.getByRole("button", { name: "Discard" }));
    expect(cell("Payments: View")).toBeChecked();
    expect(save()).toBeDisabled();
  });

  it("asks before switching role with unsaved changes, and stays when cancelled", async () => {
    vi.stubGlobal("fetch", api({ it_admin: ["payments.view"], coordinator: [] }));
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<PermissionMatrix catalogue={CATALOGUE} />);
    await waitFor(() => expect(cell("Payments: View")).toBeChecked());
    fireEvent.click(cell("Payments: Add"));
    fireEvent.change(screen.getByLabelText("Role"), { target: { value: "coordinator" } });
    expect(confirm).toHaveBeenCalled();
    expect((screen.getByLabelText("Role") as HTMLSelectElement).value).toBe("it_admin");
    expect(cell("Payments: Add")).toBeChecked();
    confirm.mockReturnValue(true);
    fireEvent.change(screen.getByLabelText("Role"), { target: { value: "coordinator" } });
    await waitFor(() => expect(cell("Payments: View")).not.toBeChecked());
    expect(cell("Payments: Add")).not.toBeChecked();
  });

  it("shows super_admin read-only with every cell held", async () => {
    vi.stubGlobal("fetch", api({ super_admin: ["payments.add", "payments.view", "reports.telecaller.download", "reports.telecaller.view"] }));
    render(<PermissionMatrix catalogue={CATALOGUE} />);
    fireEvent.change(screen.getByLabelText("Role"), { target: { value: "super_admin" } });
    await waitFor(() => expect(cell("Payments: Add")).toBeChecked());
    expect(cell("Payments: Add")).toBeDisabled();
    expect(screen.getByText(/always holds every permission/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save changes" })).toBeNull();
  });

  it("shows a refused save as an alert and keeps the edit", async () => {
    const conflict = () => new Response(JSON.stringify({ detail: "These permissions were changed by someone else. Reload and try again." }), { status: 409 });
    vi.stubGlobal("fetch", api({ it_admin: [] }, conflict));
    render(<PermissionMatrix catalogue={CATALOGUE} />);
    await waitFor(() => expect(cell("Payments: View")).toBeEnabled());
    fireEvent.click(cell("Payments: View"));
    fireEvent.click(save());
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("changed by someone else"));
    expect(cell("Payments: View")).toBeChecked();
    expect(screen.getByRole("button", { name: "Reload" })).toBeInTheDocument();
  });

  it("shows a failed read with a retry", async () => {
    const fetchMock = vi.fn().mockRejectedValueOnce(new TypeError("offline")).mockResolvedValue(new Response(JSON.stringify({ role: "it_admin", permissions: ["payments.view"], editable: true })));
    vi.stubGlobal("fetch", fetchMock);
    render(<PermissionMatrix catalogue={CATALOGUE} />);
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("could not be loaded"));
    expect(screen.queryByRole("table")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(cell("Payments: View")).toBeChecked());
  });
});
