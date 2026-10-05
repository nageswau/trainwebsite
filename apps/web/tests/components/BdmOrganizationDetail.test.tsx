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
  courses_interested: null, student_count: null, address: null, profile: null,
  pipeline: { stage: "prospect", stage_label: "College Prospect", lost: null, agent_status: null, steps: [] }, created_by_name: "Asha", archived_at: null, created_at: "2026-10-03T00:00:00Z", updated_at: "2026-10-03T00:00:00Z",
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

  it("drops ?created=1 from the address once the message is shown, without a server round trip (browser QA-08, simplify A8)", () => {
    const replaceState = vi.spyOn(window.history, "replaceState");
    render(<BdmOrganizationDetail initial={org()} basePath="/bdm/organizations" created />);
    expect(screen.getByRole("status")).toHaveTextContent("Organization ORG-000001 created.");
    expect(replaceState).toHaveBeenCalledWith(null, "", "/bdm/organizations/o1");
    expect(router.replace).not.toHaveBeenCalled();
    replaceState.mockRestore();
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

  it("moves focus to the message when the control that was used disappears (simplify review A5)", async () => {
    const archived = org({ archived: true, archived_at: "2026-10-03T01:00:00Z", permissions: perms({ can_restore: true }) });
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ organization: archived }))));
    render(<BdmOrganizationDetail initial={org({ permissions: perms({ can_edit: true, can_archive: true }) })} basePath="/bdm/organizations" />);
    fireEvent.click(screen.getByRole("button", { name: "Archive" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, archive" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveFocus());
  });

  it("shows real meeting times in IST (bdm-006 AC9)", () => {
    render(<BdmOrganizationDetail initial={org({ last_meeting_at: "2030-01-07T04:30:00Z", next_meeting_at: null })} basePath="/bdm/organizations" />);
    const details = screen.getByRole("region", { name: "Details" });
    expect(within(details).getByText("Last meeting").nextElementSibling).toHaveTextContent(/07 Jan 2030, 10:00 IST/);
    expect(within(details).getByText("Next meeting").nextElementSibling).toHaveTextContent("—");
  });

  it("offers Add appointment only to the assigned BDM on the BDM portal", () => {
    const { unmount } = render(<BdmOrganizationDetail initial={org({ permissions: perms({ can_edit: true }) })} basePath="/bdm/organizations" />);
    expect(screen.getByRole("link", { name: "Add appointment" })).toHaveAttribute("href", "/bdm/appointments/new?organization=o1");
    unmount();
    render(<BdmOrganizationDetail initial={org({ permissions: perms({ can_edit: true }) })} basePath="/bdm/manager/organizations" />);
    expect(screen.queryByRole("link", { name: "Add appointment" })).toBeNull();
  });
});

describe("BdmOrganizationDetail profile (bdm-003 AC1, AC10, §12.2 F3-F5, F8)", () => {
  it("shows the type's section under its own heading, with grades in words and line breaks kept", () => {
    render(
      <BdmOrganizationDetail
        initial={org({ org_type: "school", address: "1 Main Rd\nKochi", profile: { kind: "school", board: "State", school_type: null, grade_from: -1, grade_to: 12 } })}
        basePath="/bdm/organizations"
      />,
    );
    const details = screen.getByRole("region", { name: "Details" });
    expect(within(details).getByRole("heading", { level: 4, name: "School details" })).toBeInTheDocument();
    expect(within(details).getByText("Board").nextElementSibling).toHaveTextContent("State board");
    expect(within(details).getByText("School type").nextElementSibling).toHaveTextContent("—");
    expect(within(details).getByText("Grades").nextElementSibling).toHaveTextContent("LKG–12");
    const address = within(details).getByText("Address").nextElementSibling!;
    expect(address.textContent).toBe("1 Main Rd\nKochi");
    expect(address.firstElementChild).toHaveStyle({ whiteSpace: "pre-line" });
  });

  it("shows the empty line, with the Edit hint only when allowed (Review Focus 1)", () => {
    const empty = { kind: "college" as const, affiliation: null, college_type: null, courses: null };
    const { unmount } = render(<BdmOrganizationDetail initial={org({ profile: empty })} basePath="/bdm/organizations" />);
    expect(screen.getByText("No college details yet.")).toBeInTheDocument();
    unmount();
    render(<BdmOrganizationDetail initial={org({ permissions: perms({ can_edit: true }), profile: empty })} basePath="/bdm/organizations" />);
    expect(screen.getByText("No college details yet. Use Edit to add them.")).toBeInTheDocument();
  });

  it("shows Commission as text for agents, an unknown value as it is, and nothing for common-only types", () => {
    const { unmount } = render(
      <BdmOrganizationDetail initial={org({ org_type: "agent", profile: { kind: "agent", country: "India", territory: null, source: "tv_ad", staff_count: 4 } })} basePath="/bdm/organizations" />,
    );
    expect(screen.getByText("Commission: Available after onboarding")).toBeInTheDocument();
    expect(screen.getByText("Source").nextElementSibling).toHaveTextContent("tv_ad");
    unmount();
    render(<BdmOrganizationDetail initial={org({ org_type: "corporate", profile: null })} basePath="/bdm/organizations" />);
    expect(screen.queryByRole("heading", { level: 4 })).toBeNull();
  });
});

describe("BdmOrganizationDetail activity timeline (bdm-009, QA9-01)", () => {
  const timeline = { items: [], total: 0, limit: 20, offset: 0 };
  const logged = { id: "a1", organization: { id: "o1", code: "ORG-000001", name: "St Mary", org_type: "college" }, bdm: { id: "b1", full_name: "Asha" },
    contact_id: null, contact_name: null, contact_removed: false, channel: "visit", direction: null, occurred_at: "2026-10-03T05:00:00Z",
    note: null, created_at: "2026-10-03T05:00:00Z", updated_at: "2026-10-03T05:00:00Z", permissions: { can_change: true } };

  it("has exactly one status live region, and logging an activity announces in it", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(logged, 201))));
    render(<BdmOrganizationDetail initial={org({ permissions: perms({ can_edit: true }) })} basePath="/bdm/organizations" activities={timeline} />);
    expect(screen.getAllByRole("status")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Log activity" }));
    fireEvent.change(screen.getByLabelText("Channel (required)"), { target: { value: "visit" } });
    fireEvent.click(screen.getByRole("button", { name: "Save activity" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Activity logged."));
    expect(screen.getAllByRole("status")).toHaveLength(1);
    expect(document.activeElement).toBe(screen.getByRole("status"));
    fireEvent.click(screen.getByRole("button", { name: "Log activity" })); // the next action clears the old notice (QA9-03)
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });
});
