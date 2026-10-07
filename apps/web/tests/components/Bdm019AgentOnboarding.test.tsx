import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminSchoolOnboardingRequests from "@/components/AdminSchoolOnboardingRequests";
import BdmOrganizationOnboarding from "@/components/BdmOrganizationOnboarding";
import BdmOrganizationPipeline from "@/components/BdmOrganizationPipeline";
import BdmOrganizationProfileDetails from "@/components/BdmOrganizationProfileDetails";
import type { AgentLink, OnboardingItem, OrgOnboarding } from "@/lib/bdmOnboarding";
import type { Organization } from "@/lib/bdmOrganizations";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const pending = { id: "r1", status: "pending" as const, created_at: "2026-10-07T05:00:00Z", resolved_at: null, reject_reason: null };
const agency: AgentLink = {
  name: "Globe Admissions", prefix: "GLOBE", status: "active", master_login: true, staff_count: 3, counts: { students: 4, applications: 7, enrollments: 1 },
};
const org = (onboarding: OrgOnboarding | null, over: Partial<Organization> = {}): Organization => ({
  id: "o1", code: "ORG-000009", name: "Globe", org_type: "agent", bdm_type: "agent", city: "Kochi", state: null, existing_partner: false,
  assigned_bdm: { id: "b1", full_name: "Asha", active: true }, primary_contact: null, archived: false, last_meeting_at: null, next_meeting_at: null,
  permissions: { can_edit: true, can_archive: true, can_restore: false, can_reassign: false }, phone: null, email: null, website: null,
  courses_interested: null, student_count: null, address: null,
  profile: { kind: "agent", country: "India", territory: null, source: null, staff_count: 5 },
  pipeline: { stage: "agreement_signed", stage_label: "Agreement Signed", lost: null, agent_status: "Agreement", steps: [] }, contacts: [],
  created_by_name: "Asha", archived_at: null, created_at: "2026-10-03T00:00:00Z", updated_at: "2026-10-03T00:00:00Z", onboarding, ...over,
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("bdm-019 agent onboarding card", () => {
  const card = (o: Organization) => render(<BdmOrganizationOnboarding organization={o} onRequested={vi.fn()} />);

  it("shows the linked agency's live summary, never names", () => {
    card(org({ request: { ...pending, status: "completed", resolved_at: "2026-10-07T06:00:00Z" }, school: null, agent: agency, can_request: false }));
    const region = screen.getByRole("region", { name: "Agent onboarding" });
    expect(region).toHaveTextContent("Linked to Globe Admissions (code GLOBE). Status: Active.");
    expect(region).toHaveTextContent("Master login: Created · Staff logins: 3");
    expect(within(region).queryByRole("button")).toBeNull();
  });

  it("says a suspended agency is inactive, and a pending request waits for Overseas Admin", () => {
    card(org({ request: null, school: null, agent: { ...agency, status: "suspended", master_login: false, staff_count: 0 }, can_request: false }));
    expect(screen.getByRole("region", { name: "Agent onboarding" })).toHaveTextContent("Status: Suspended.");
    expect(screen.getByRole("region", { name: "Agent onboarding" })).toHaveTextContent("Master login: Not yet · Staff logins: 0");
    cleanup();
    card(org({ request: pending, school: null, agent: null, can_request: false }));
    expect(screen.getByRole("region", { name: "Agent onboarding" })).toHaveTextContent(/Waiting for Overseas Admin to link the agent organization\./);
  });

  it("explains the agreement rule before a request is possible", () => {
    card(org({ request: null, school: null, agent: null, can_request: false }));
    expect(screen.getByText("Available once the agreement is signed.")).toBeInTheDocument();
    cleanup();
    card(org({ request: null, school: null, agent: null, can_request: true }));
    expect(screen.getByText(/Ready to hand over: Overseas Admin will link the agent organization/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Request onboarding" })).toBeInTheDocument();
  });
});

describe("bdm-019 pipeline counts and profile", () => {
  it("shows a counted volume step's figure", () => {
    const steps = [
      { key: "active_agent", label: "Active Agent", kind: "live" as const, state: "done" as const, count: null },
      { key: "students", label: "Students", kind: "volume" as const, state: "done" as const, count: 4 },
      { key: "enrollments", label: "Enrollments", kind: "volume" as const, state: "upcoming" as const, count: 0 },
    ];
    render(<BdmOrganizationPipeline organization={org(null, { pipeline: { ...org(null).pipeline, agent_status: "Active", steps } })} onChanged={vi.fn()} />);
    const list = screen.getByRole("list", { name: "Pipeline stages" });
    expect(within(list).getByText("Students").closest("li")).toHaveTextContent("Students4Done");
    expect(within(list).getByText("Enrollments").closest("li")).toHaveTextContent("Enrollments0Upcoming");
    expect(within(list).getByText("Active Agent").closest("li")).toHaveTextContent("Active AgentDone");
  });

  it("shows the live staff count beside the entered one, and no commission once linked", () => {
    render(<BdmOrganizationProfileDetails organization={org({ request: null, school: null, agent: agency, can_request: false })} />);
    expect(screen.getByText("3 live (5 entered)")).toBeInTheDocument();
    expect(screen.getByText("Commission: Not shown to BDMs (awaiting a decision)")).toBeInTheDocument();
    cleanup();
    render(<BdmOrganizationProfileDetails organization={org({ request: null, school: null, agent: null, can_request: false })} />);
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("Commission: Available after onboarding")).toBeInTheDocument();
  });

  it("QA19-02: a linked agency's live staff count shows even when no agent details were entered", () => {
    const empty = { kind: "agent" as const, country: null, territory: null, source: null, staff_count: null };
    render(<BdmOrganizationProfileDetails organization={org({ request: null, school: null, agent: agency, can_request: false }, { profile: empty })} />);
    expect(screen.queryByText(/No agent details yet/)).toBeNull();
    expect(screen.getByText("3 live")).toBeInTheDocument();
  });
});

describe("bdm-019 admin agent queue", () => {
  const item = (over: Partial<OnboardingItem> = {}): OnboardingItem => ({
    id: "r9", kind: "agent", status: "pending", note: null, created_at: "2026-10-07T05:00:00Z", resolved_at: null, resolution: null, reject_reason: null,
    requested_by: { id: "b1", full_name: "Asha" }, assigned_bdm: { id: "b1", full_name: "Asha", active: true },
    organization: { id: "o1", code: "ORG-000009", name: "Globe", city: "Kochi", state: null, address: null, phone: null, email: null, website: null, board: null, grade_from: null, grade_to: null },
    primary_contact: null, mou: null, school: null, agent_org: null, ...over,
  });
  const queue = () => render(<AdminSchoolOnboardingRequests kind="agent" selectedId={null} version={0} onUse={vi.fn()} onResolved={vi.fn()} />);

  it("lists agent requests and offers link by agent code, not a new school", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res({ items: [item()], total: 1, limit: 20, offset: 0 }));
    vi.stubGlobal("fetch", fetchMock);
    queue();
    const region = screen.getByRole("region", { name: "Agent onboarding requests" });
    expect(await within(region).findByText("ORG-000009 · Globe")).toBeInTheDocument();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/overseas-admin/bdm-onboarding-requests?status=pending&limit=20&offset=0&kind=agent");
    expect(within(region).queryByRole("button", { name: "Use for new school" })).toBeNull();
    expect(within(region).queryByRole("button", { name: "Link existing school" })).toBeNull();
    expect(within(region).getByRole("button", { name: "Link agent organization" })).toBeInTheDocument();
  });

  it("links by code and announces the result", async () => {
    const linked = item({ status: "completed", resolution: "linked", agent_org: { id: "a1", name: "Globe Admissions", prefix: "GLOBE", status: "pending" } });
    const fetchMock = vi.fn().mockResolvedValueOnce(res({ items: [item()], total: 1, limit: 20, offset: 0 })).mockResolvedValueOnce(res(linked));
    vi.stubGlobal("fetch", fetchMock);
    queue();
    fireEvent.click(await screen.findByRole("button", { name: "Link agent organization" }));
    fireEvent.change(screen.getByLabelText("Agent code"), { target: { value: "globe" } });
    fireEvent.click(screen.getByRole("button", { name: "Link agent" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("ORG-000009 is now linked to Globe Admissions (GLOBE)."));
    expect(fetchMock.mock.calls[1][0]).toBe("/api/v1/overseas-admin/bdm-onboarding-requests/r9/link-agent");
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ agent_code: "globe" });
  });

  it("shows the server's refusal and keeps the form", async () => {
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce(res({ items: [item()], total: 1, limit: 20, offset: 0 }))
      .mockResolvedValueOnce(res({ detail: { message: "This agent organization is already linked to another organization", code: "agent_org_linked" } }, 409)));
    queue();
    fireEvent.click(await screen.findByRole("button", { name: "Link agent organization" }));
    fireEvent.change(screen.getByLabelText("Agent code"), { target: { value: "GLOBE" } });
    fireEvent.click(screen.getByRole("button", { name: "Link agent" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This agent organization is already linked to another organization");
    expect(screen.getByLabelText("Agent code")).toHaveValue("GLOBE");
  });
});
