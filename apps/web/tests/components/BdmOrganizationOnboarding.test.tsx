import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmOrganizationOnboarding from "@/components/BdmOrganizationOnboarding";
import type { OrgOnboarding } from "@/lib/bdmOnboarding";
import type { Organization } from "@/lib/bdmOrganizations";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const pending = { id: "r1", status: "pending" as const, created_at: "2026-10-06T05:00:00Z", resolved_at: null, reject_reason: null };
const org = (onboarding: OrgOnboarding, over: Partial<Organization> = {}): Organization => ({
  id: "o1", code: "ORG-000001", name: "St Mary", org_type: "school", bdm_type: "school", city: "Kochi", state: null, existing_partner: false,
  assigned_bdm: { id: "b1", full_name: "Asha", active: true }, primary_contact: null, archived: false, last_meeting_at: null, next_meeting_at: null,
  permissions: { can_edit: true, can_archive: true, can_restore: false, can_reassign: false }, phone: null, email: null, website: null,
  courses_interested: null, student_count: null, address: null, profile: null,
  pipeline: { stage: "signed", stage_label: "Signed", lost: null, agent_status: null, steps: [] }, contacts: [], created_by_name: "Asha", archived_at: null,
  created_at: "2026-10-03T00:00:00Z", updated_at: "2026-10-03T00:00:00Z", onboarding, ...over,
});
const card = (o: Organization, onRequested = vi.fn()) => render(<BdmOrganizationOnboarding organization={o} onRequested={onRequested} />);

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("BdmOrganizationOnboarding (bdm-018 §6)", () => {
  it("names the linked School", () => {
    card(org({ request: { ...pending, status: "completed", resolved_at: "2026-10-06T06:00:00Z" }, school: { name: "St Mary School", school_code: "AB12CD34" }, can_request: false }));
    const region = screen.getByRole("region", { name: "School onboarding" });
    expect(region).toHaveTextContent("Onboarded as St Mary School (School ID AB12CD34).");
    expect(within(region).queryByRole("button")).toBeNull();
  });

  it("says a pending request is waiting for Overseas Admin", () => {
    card(org({ request: pending, school: null, can_request: false }));
    expect(screen.getByRole("region", { name: "School onboarding" })).toHaveTextContent(/Requested on .*Waiting for Overseas Admin to create or link the School\./);
  });

  it("shows a rejection's reason and offers to request again", () => {
    const rejected = { ...pending, status: "rejected" as const, resolved_at: "2026-10-06T06:00:00Z", reject_reason: "Board details missing" };
    card(org({ request: rejected, school: null, can_request: true }));
    expect(screen.getByText(/Not approved/)).toHaveTextContent("Board details missing");
    expect(screen.getByRole("button", { name: "Request again" })).toBeInTheDocument();
  });

  it("explains when a request is not yet possible, and is read-only for others", () => {
    card(org({ request: null, school: null, can_request: false }));
    expect(screen.getByText("Available once the MoU is Signed or Active.")).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
    cleanup();
    card(org({ request: null, school: null, can_request: false }, { permissions: { can_edit: false, can_archive: false, can_restore: false, can_reassign: true } }));
    expect(screen.getByText("Not requested yet.")).toBeInTheDocument();
  });

  it("sends the request with the optional note and hands the organization back", async () => {
    const next = org({ request: pending, school: null, can_request: false });
    const fetchMock = vi.fn().mockResolvedValue(res({ organization: next }, 201));
    vi.stubGlobal("fetch", fetchMock);
    const onRequested = vi.fn();
    card(org({ request: null, school: null, can_request: true }), onRequested);
    fireEvent.click(screen.getByRole("button", { name: "Request onboarding" }));
    fireEvent.change(screen.getByLabelText("Note for Overseas Admin (optional)"), { target: { value: "Ready from June" } });
    fireEvent.click(screen.getByRole("button", { name: "Send request" }));
    expect(screen.getByRole("button", { name: "Sending…" })).toBeDisabled();
    await waitFor(() => expect(onRequested).toHaveBeenCalledWith(next));
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/bdm/organizations/o1/onboarding-request");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ note: "Ready from June" });
  });

  it("shows the server's refusal and keeps the form", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail: { message: "This organization already has an onboarding request waiting", code: "request_pending" } }, 409)));
    card(org({ request: null, school: null, can_request: true }));
    fireEvent.click(screen.getByRole("button", { name: "Request onboarding" }));
    fireEvent.click(screen.getByRole("button", { name: "Send request" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This organization already has an onboarding request waiting");
    expect(screen.getByRole("button", { name: "Send request" })).toBeEnabled();
  });

  it("QA18-01: a server error says the outcome is unknown instead of a generic message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("Internal Server Error", { status: 500 })));
    card(org({ request: null, school: null, can_request: true }));
    fireEvent.click(screen.getByRole("button", { name: "Request onboarding" }));
    fireEvent.click(screen.getByRole("button", { name: "Send request" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The request could not be confirmed. Reload the page to check before trying again.");
  });

  it("cancel closes the form and returns focus to the button", async () => {
    card(org({ request: null, school: null, can_request: true }));
    fireEvent.click(screen.getByRole("button", { name: "Request onboarding" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Request onboarding" })).toHaveFocus());
  });
});
