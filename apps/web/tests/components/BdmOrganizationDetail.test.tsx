import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmOrganizationDetail from "@/components/BdmOrganizationDetail";
import type { Organization } from "@/lib/bdmOrganizations";

const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const perms = (p: Partial<Organization["permissions"]> = {}) => ({ can_edit: false, can_archive: false, can_restore: false, can_reassign: false, ...p });
const org = (over: Partial<Organization> = {}): Organization => ({
  id: "o1", code: "ORG-000001", name: "St Mary", org_type: "college", bdm_type: "college", city: "Kochi", state: null, existing_partner: false,
  assigned_bdm: { id: "b1", full_name: "Asha", active: true }, primary_contact: { name: "Dr Rao", designation: "Principal", phone: null, email: null },
  archived: false, last_meeting_at: null, next_meeting_at: null, permissions: perms(), phone: null, email: null, website: "javascript:alert(1)",
  courses_interested: null, student_count: null, created_by_name: "Asha", archived_at: null, created_at: "2026-10-03T00:00:00Z", updated_at: "2026-10-03T00:00:00Z",
  contacts: [{ id: "c1", name: "Dr Rao", designation: "Principal", role: "principal", phone: null, email: null, is_primary: true }, { id: "c2", name: "Ms Iyer", designation: null, role: null, phone: null, email: null, is_primary: false }],
  ...over,
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  router.replace.mockClear();
});

describe("BdmOrganizationDetail (bdm-002 AC3-AC6, §12.2)", () => {
  it("is read-only without permissions; dashes for meetings; unsafe website is plain text", () => {
    render(<BdmOrganizationDetail initial={org()} basePath="/bdm/organizations" />);
    expect(screen.queryByRole("button", { name: /Edit|Archive|Restore|Reassign|Add contact/ })).toBeNull();
    const details = screen.getByRole("region", { name: "Details" });
    expect(within(details).getByText("Last meeting").nextElementSibling).toHaveTextContent("—");
    expect(within(details).getByText("Contact person").nextElementSibling).toHaveTextContent("Dr Rao");
    expect(screen.queryByRole("link", { name: /javascript/ })).toBeNull();
  });

  it("links a safe website in a new tab", () => {
    render(<BdmOrganizationDetail initial={org({ website: "https://mary.edu" })} basePath="/bdm/organizations" />);
    const link = screen.getByRole("link", { name: /mary\.edu/ });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("archives after an inline confirm, Escape cancels and returns focus", async () => {
    const archived = org({ archived: true, archived_at: "2026-10-03T01:00:00Z", permissions: perms() });
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ organization: archived }))));
    render(<BdmOrganizationDetail initial={org({ permissions: perms({ can_edit: true, can_archive: true }) })} basePath="/bdm/organizations" />);
    const trigger = screen.getByRole("button", { name: "Archive" });
    fireEvent.click(trigger);
    const group = screen.getByRole("group", { name: "Confirm archive" });
    fireEvent.keyDown(group, { key: "Escape" });
    await waitFor(() => expect(trigger).toHaveFocus());
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole("button", { name: "Yes, archive" }));
    expect(await screen.findByText("Archived", { selector: ".badge" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Organization archived.");
  });

  it("shows Restore for a manager on an archived organization", () => {
    render(<BdmOrganizationDetail initial={org({ archived: true, permissions: perms({ can_restore: true }) })} basePath="/bdm/manager/organizations" />);
    expect(screen.getByRole("button", { name: "Restore" })).toBeInTheDocument();
  });

  it("disables deleting the last contact and explains why", () => {
    render(<BdmOrganizationDetail initial={org({ permissions: perms({ can_edit: true }), contacts: [org().contacts[0]] })} basePath="/bdm/organizations" />);
    expect(screen.getByRole("button", { name: "Delete Dr Rao" })).toBeDisabled();
    expect(screen.getByText("An organization needs at least one contact.")).toBeInTheDocument();
  });

  it("shows a refused action's message and re-renders from a returned organization", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "Restore this organization first" }, 409))));
    render(<BdmOrganizationDetail initial={org({ permissions: perms({ can_edit: true, can_archive: true }) })} basePath="/bdm/organizations" />);
    fireEvent.click(screen.getByRole("button", { name: "Archive" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, archive" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Restore this organization first");
  });

  it("announces a just-created organization", () => {
    render(<BdmOrganizationDetail initial={org()} basePath="/bdm/organizations" created />);
    expect(screen.getByRole("status")).toHaveTextContent("Organization ORG-000001 created.");
  });

  it("hides Archive while the edit form is open (browser QA-14)", () => {
    render(<BdmOrganizationDetail initial={org({ permissions: perms({ can_edit: true, can_archive: true }) })} basePath="/bdm/organizations" />);
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.queryByRole("button", { name: "Archive" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("button", { name: "Archive" })).toBeInTheDocument();
  });

  it("returns focus to Edit when the edit form closes (browser QA-12)", async () => {
    render(<BdmOrganizationDetail initial={org({ permissions: perms({ can_edit: true }) })} basePath="/bdm/organizations" />);
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Edit" })).toHaveFocus());
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.click(screen.getByRole("button", { name: "Save changes" })); // no change: closes without a request
    await waitFor(() => expect(screen.getByRole("button", { name: "Edit" })).toHaveFocus());
  });

  it("drops ?created=1 from the address once the message is shown, so a refresh does not repeat it (browser QA-08)", () => {
    render(<BdmOrganizationDetail initial={org()} basePath="/bdm/organizations" created />);
    expect(screen.getByRole("status")).toHaveTextContent("Organization ORG-000001 created.");
    expect(router.replace).toHaveBeenCalledWith("/bdm/organizations/o1", { scroll: false });
  });

  it("does not touch the address when nothing was just created", () => {
    render(<BdmOrganizationDetail initial={org()} basePath="/bdm/organizations" />);
    expect(router.replace).not.toHaveBeenCalled();
  });

  it("says when a save had nothing to change (browser QA-13)", async () => {
    render(<BdmOrganizationDetail initial={org({ permissions: perms({ can_edit: true }) })} basePath="/bdm/organizations" />);
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("No changes to save.")).toBeInTheDocument();
  });

  it("styles Back to organizations as a link (browser QA-03)", () => {
    render(<BdmOrganizationDetail initial={org()} basePath="/bdm/organizations" />);
    expect(screen.getByRole("link", { name: "Back to organizations" })).toHaveStyle({ textDecoration: "underline" });
  });
});
