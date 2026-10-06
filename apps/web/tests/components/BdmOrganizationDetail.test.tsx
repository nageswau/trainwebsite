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

describe("BdmOrganizationDetail -- bdm-004 placement (QA4-05)", () => {
  it("shows the pipeline first, then Details and Contacts, then the stage history", () => {
    render(<BdmOrganizationDetail initial={org()} basePath="/bdm/organizations" stageHistory={{ items: [], total: 0, limit: 20, offset: 0 }} />);
    const before = (a: HTMLElement, b: HTMLElement) => Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
    const pipeline = screen.getByRole("region", { name: "Pipeline" });
    const details = screen.getByRole("region", { name: "Details" });
    const contacts = screen.getByRole("list", { name: "Contacts" });
    const history = screen.getByRole("region", { name: "Stage history" });
    expect([before(pipeline, details), before(details, contacts), before(contacts, history)]).toEqual([true, true, true]);
  });
});

describe("BdmOrganizationDetail -- bdm-018 school onboarding", () => {
  const school = (onboarding: Organization["onboarding"]) => org({ org_type: "school", bdm_type: "school", permissions: perms({ can_edit: true }), onboarding });

  it("shows the onboarding card after the MoU card for School organizations only", () => {
    render(<BdmOrganizationDetail initial={school({ request: null, school: null, can_request: true })} basePath="/bdm/organizations" mou={{ current: null, can_start: false }} />);
    const mou = screen.getByRole("region", { name: "MoU" });
    expect(mou.nextElementSibling).toBe(screen.getByRole("region", { name: "School onboarding" }));
    cleanup();
    render(<BdmOrganizationDetail initial={org({ onboarding: null })} basePath="/bdm/organizations" />);
    expect(screen.queryByRole("region", { name: "School onboarding" })).toBeNull();
  });

  it("a request re-renders the page from the returned organization and announces it", async () => {
    const pendingOrg = school({ request: { id: "r1", status: "pending", created_at: "2026-10-06T05:00:00Z", resolved_at: null, reject_reason: null }, school: null, can_request: false });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ organization: pendingOrg }, 201)));
    render(<BdmOrganizationDetail initial={school({ request: null, school: null, can_request: true })} basePath="/bdm/organizations" />);
    fireEvent.click(screen.getByRole("button", { name: "Request onboarding" }));
    fireEvent.click(screen.getByRole("button", { name: "Send request" }));
    expect(await screen.findByText("Onboarding requested. Overseas Admin will create or link the School.")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "School onboarding" })).toHaveTextContent("Waiting for Overseas Admin");
  });
});

describe("BdmOrganizationDetail -- bdm-005 MoU card", () => {
  it("places the MoU card right after the pipeline, and only when the page read it", () => {
    render(<BdmOrganizationDetail initial={org()} basePath="/bdm/organizations" mou={{ current: null, can_start: false }} />);
    const pipeline = screen.getByRole("region", { name: "Pipeline" });
    const mou = screen.getByRole("region", { name: "MoU" });
    expect(Boolean(pipeline.compareDocumentPosition(mou) & Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true);
    expect(mou.nextElementSibling).toBe(screen.getByRole("region", { name: "Details" }));
    cleanup();
    render(<BdmOrganizationDetail initial={org()} basePath="/bdm/organizations" />);
    expect(screen.queryByRole("region", { name: "MoU" })).toBeNull();
  });

  it("QA5-06: tells the MoU card why it is read-only on a lost or archived organization", () => {
    const lost = { stage: "prospect", stage_label: "College Prospect", lost: { at: "2026-10-01T00:00:00Z", reason: "No budget" }, agent_status: null, steps: [] };
    render(<BdmOrganizationDetail initial={org({ pipeline: lost })} basePath="/bdm/organizations" mou={{ current: null, can_start: false }} />);
    expect(within(screen.getByRole("region", { name: "MoU" })).getByText("This organization is marked lost, so its MoU is read-only.")).toBeInTheDocument();
    cleanup();
    render(<BdmOrganizationDetail initial={org({ archived: true })} basePath="/bdm/organizations" mou={{ current: null, can_start: false }} />);
    expect(within(screen.getByRole("region", { name: "MoU" })).getByText("This organization is archived, so its MoU is read-only.")).toBeInTheDocument();
    cleanup();
    render(<BdmOrganizationDetail initial={org()} basePath="/bdm/organizations" mou={{ current: null, can_start: false }} />);
    expect(within(screen.getByRole("region", { name: "MoU" })).queryByText(/so its MoU is read-only/)).toBeNull();
  });

  it("re-reads the organization when signing moved the pipeline", async () => {
    const moved = org({ pipeline: { stage: "mou_signed", stage_label: "MoU Signed", lost: null, agent_status: null, steps: [] } });
    const signed = { id: "m1", status: "signed", status_label: "Signed", pipeline_on_sign: null, permissions: { can_edit: true, can_upload: true, can_renew: false } };
    const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(async (url) => {
      if (url === "/api/v1/bdm/organizations/o1") return res({ organization: moved });
      if (url === "/api/v1/bdm/organizations/o1/mou") return res({ mou: { ...signed, organization: { id: "o1" } } });
      return res({});
    });
    vi.stubGlobal("fetch", fetchMock);
    const current = {
      id: "m1", organization: { id: "o1", code: "ORG-000001", name: "St Mary", bdm_type: "college" }, assigned_bdm: { id: "b1", full_name: "Asha", active: true },
      status: "under_negotiation", status_label: "Under Negotiation", status_changed_at: "2026-10-01T00:00:00Z", signed_on: null, valid_until: null, reference: null,
      has_document: false, is_current: true, proposal_sent_on: null, valid_from: null, notes: null, document: null, expired_on: null,
      created_by: { id: "b1", full_name: "Asha" }, permissions: { can_edit: true, can_upload: true, can_renew: false }, pipeline_on_sign: { key: "mou_signed", label: "MoU Signed" },
      created_at: "2026-10-01T00:00:00Z", updated_at: "2026-10-01T00:00:00Z",
    } as const;
    render(<BdmOrganizationDetail initial={org({ permissions: perms({ can_edit: true }) })} basePath="/bdm/organizations" mou={{ current, can_start: false }} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit MoU" }));
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "signed" } });
    fireEvent.change(screen.getByLabelText("Signed date (required)"), { target: { value: "2026-10-06" } });
    fireEvent.click(screen.getByRole("button", { name: "Save MoU" }));
    fireEvent.click(within(screen.getByRole("group", { name: "Confirm signing" })).getByRole("button", { name: "Yes, save" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([url, init]) => url === "/api/v1/bdm/organizations/o1" && (init as RequestInit | undefined)?.method === "GET")).toBe(true));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("MoU saved. The pipeline moved to MoU Signed."));
  });
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

describe("BdmOrganizationDetail leads (bdm-017 L6)", () => {
  const leads = { items: [], total: 0, limit: 20, offset: 0 };
  const saved = { id: "l1", name: "Asha Nair", email: "asha@example.com", phone: null, interest: "B.Tech", status: "new", bdm: { id: "b1", full_name: "Asha" },
    converted: false, created_at: "2026-10-05T04:00:00Z" };

  it("the assigned BDM adds a lead and the profile's one live region announces it", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(saved, 201))));
    render(<BdmOrganizationDetail initial={org({ permissions: perms({ can_edit: true }) })} basePath="/bdm/organizations" leads={leads} />);
    fireEvent.click(screen.getByRole("button", { name: "Add lead" }));
    fireEvent.change(screen.getByLabelText("Student name (required)"), { target: { value: "Asha Nair" } });
    fireEvent.change(screen.getByLabelText("Email (required)"), { target: { value: "asha@example.com" } });
    fireEvent.change(screen.getByLabelText("Interest (required)"), { target: { value: "B.Tech" } });
    fireEvent.click(screen.getByRole("button", { name: "Save lead" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Lead added."));
    expect(screen.getAllByRole("status")).toHaveLength(1);
    expect(screen.getByRole("heading", { name: "Leads (1)" })).toBeInTheDocument();
  });

  it("the manager view and an unassigned BDM read leads but cannot add", () => {
    render(<BdmOrganizationDetail initial={org({ permissions: perms({ can_reassign: true }) })} basePath="/bdm/manager/organizations" leads={leads} />);
    expect(screen.getByRole("heading", { name: "Leads (0)" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add lead" })).toBeNull();
    cleanup();
    render(<BdmOrganizationDetail initial={org({ permissions: perms() })} basePath="/bdm/organizations" leads={leads} />);
    expect(screen.queryByRole("button", { name: "Add lead" })).toBeNull();
  });

  it("no leads prop, no section (pages that don't read leads)", () => {
    render(<BdmOrganizationDetail initial={org()} basePath="/bdm/organizations" />);
    expect(screen.queryByRole("heading", { name: /^Leads/ })).toBeNull();
  });
});
