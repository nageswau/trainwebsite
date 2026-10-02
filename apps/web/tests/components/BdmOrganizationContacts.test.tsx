import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmOrganizationContacts from "@/components/BdmOrganizationContacts";
import type { Organization } from "@/lib/bdmOrganizations";

// bdm-002 (C1, C10; spec §6.2): contacts are added, edited, made primary and deleted inline; every success re-renders from the
// organization the API returns.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const RAO = { id: "c1", name: "Dr Rao", designation: "Principal", role: "principal" as const, phone: null, email: null, is_primary: true };
const IYER = { id: "c2", name: "Ms Iyer", designation: null, role: null, phone: "+91 98", email: null, is_primary: false };
const org = (contacts = [RAO, IYER], canEdit = true) =>
  ({ id: "o1", code: "ORG-000001", contacts, permissions: { can_edit: canEdit, can_archive: canEdit, can_restore: false, can_reassign: false } }) as unknown as Organization;
function serve(...responses: Response[]) {
  const mock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(() => Promise.resolve(responses.shift()!));
  vi.stubGlobal("fetch", mock);
  return mock;
}
const call = (mock: ReturnType<typeof serve>, i = 0) => {
  const [url, init] = mock.mock.calls[i] as unknown as [string, RequestInit];
  return { url, method: init.method, body: init.body ? JSON.parse(String(init.body)) : undefined };
};
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("BdmOrganizationContacts", () => {
  it("lists contacts with the primary marked and dashes for blanks; read-only without edit rights", () => {
    render(<BdmOrganizationContacts organization={org(undefined, false)} onChanged={vi.fn()} />);
    const list = screen.getByRole("list", { name: "Contacts" });
    expect(within(list).getAllByRole("listitem")[0]).toHaveTextContent("Dr Rao");
    expect(within(list).getAllByRole("listitem")[0]).toHaveTextContent("Primary");
    expect(within(list).getAllByRole("listitem")[1]).toHaveTextContent("—");
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("adds a contact", async () => {
    const updated = org([RAO, IYER, { ...IYER, id: "c3", name: "Mr Das" }]);
    const mock = serve(res({ organization: updated }, 201));
    const onChanged = vi.fn();
    render(<BdmOrganizationContacts organization={org()} onChanged={onChanged} />);
    fireEvent.click(screen.getByRole("button", { name: "Add contact" }));
    fireEvent.change(screen.getByLabelText("Contact name (required)"), { target: { value: "Mr Das" } });
    fireEvent.change(screen.getByLabelText("Role"), { target: { value: "hod" } });
    fireEvent.click(screen.getByRole("button", { name: "Save contact" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(updated, "Contact added."));
    expect(call(mock)).toEqual({ url: "/api/v1/bdm/organizations/o1/contacts", method: "POST", body: { name: "Mr Das", role: "hod" } });
  });

  it("refuses a blank name before sending", () => {
    const mock = serve();
    render(<BdmOrganizationContacts organization={org()} onChanged={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Add contact" }));
    fireEvent.click(screen.getByRole("button", { name: "Save contact" }));
    expect(screen.getByText("Contact name is required")).toBeInTheDocument();
    expect(mock).not.toHaveBeenCalled();
  });

  it("edits only the changed fields", async () => {
    const mock = serve(res({ organization: org() }));
    const onChanged = vi.fn();
    render(<BdmOrganizationContacts organization={org()} onChanged={onChanged} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit Ms Iyer" }));
    fireEvent.change(screen.getByLabelText("Designation"), { target: { value: "HOD CSE" } });
    fireEvent.click(screen.getByRole("button", { name: "Save contact" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(expect.anything(), "Contact updated."));
    expect(call(mock)).toEqual({ url: "/api/v1/bdm/organizations/o1/contacts/c2", method: "PATCH", body: { designation: "HOD CSE" } });
  });

  it("makes a contact primary", async () => {
    const mock = serve(res({ organization: org() }));
    const onChanged = vi.fn();
    render(<BdmOrganizationContacts organization={org()} onChanged={onChanged} />);
    expect(screen.queryByRole("button", { name: "Make Dr Rao primary" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Make Ms Iyer primary" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(expect.anything(), "Primary contact changed."));
    expect(call(mock)).toEqual({ url: "/api/v1/bdm/organizations/o1/contacts/c2", method: "PATCH", body: { is_primary: true } });
  });

  it("deletes after an inline confirm; Escape cancels and returns focus", async () => {
    const mock = serve(res({ organization: org([RAO]) }));
    const onChanged = vi.fn();
    render(<BdmOrganizationContacts organization={org()} onChanged={onChanged} />);
    const trigger = screen.getByRole("button", { name: "Delete Ms Iyer" });
    fireEvent.click(trigger);
    fireEvent.keyDown(screen.getByRole("group", { name: "Confirm delete" }), { key: "Escape" });
    await waitFor(() => expect(trigger).toHaveFocus());
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(org([RAO]), "Contact deleted."));
    expect(call(mock)).toEqual({ url: "/api/v1/bdm/organizations/o1/contacts/c2", method: "DELETE", body: undefined });
  });

  it("shows a refusal as an alert", async () => {
    serve(res({ detail: "Restore this organization first" }, 409));
    render(<BdmOrganizationContacts organization={org()} onChanged={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Make Ms Iyer primary" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Restore this organization first");
  });

  it("keeps keyboard focus after a delete or an add (final review M5, spec F6)", async () => {
    serve(res({ organization: org([RAO]) }), res({ organization: org() }, 201));
    const { rerender } = render(<BdmOrganizationContacts organization={org()} onChanged={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Delete Ms Iyer" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Add contact" })).toHaveFocus());
    rerender(<BdmOrganizationContacts organization={org([RAO])} onChanged={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Add contact" }));
    fireEvent.change(screen.getByLabelText("Contact name (required)"), { target: { value: "Ms Iyer" } });
    fireEvent.click(screen.getByRole("button", { name: "Save contact" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Add contact" })).toHaveFocus());
  });
});
