import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import MeetingRequestDecide from "@/components/MeetingRequestDecide";
import type { MeetingRequest } from "@/lib/meetingRequests";
import type { Organization } from "@/lib/bdmOrganizations";

const router = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

const FUTURE = "2030-01-02T05:30:00+00:00"; // 11:00 IST
const request = (over: Partial<MeetingRequest> = {}): MeetingRequest => ({
  id: "r1", code: "MRQ-000001", request_type: "school", type_label: "School meeting", bdm_type: "school", organization_name: "St Mary",
  person_name: "Ms Iyer", contact_phone: "9876543210", contact_email: null, proposed_at: FUTURE, mode: "In person", location: "Main block",
  purpose: "Career guidance talk", remarks: "Grade 12", status: "pending", requester: { id: "t1", full_name: "Tara" }, bdm: null,
  appointment: null, decline_reason: null, decided_at: null, created_at: FUTURE, permissions: { can_accept: true, can_decline: true }, ...over,
});
const org: Organization = {
  id: "o1", code: "ORG-000001", name: "St Mary", contacts: [{ id: "c1", name: "Ms Iyer", designation: null, role: null, phone: null, email: null, is_primary: true }],
} as unknown as Organization;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  router.push.mockReset();
  router.refresh.mockReset();
});

describe("MeetingRequestDecide (tel-019)", () => {
  it("starts the booking from the request and accepts through its URL (MR9)", async () => {
    const fetch = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>((url) =>
      Promise.resolve(String(url).includes("/organizations/") ? res({ organization: org }) : res({ appointment: { id: "a9" }, meeting_request: request() })));
    vi.stubGlobal("fetch", fetch);
    render(<MeetingRequestDecide request={request()} bdmType="school" initialOrganization={org} />);
    expect((screen.getByLabelText("Type (required)") as HTMLSelectElement).value).toBe("school_meeting");
    expect((screen.getByLabelText("Date and time (IST) (required)") as HTMLInputElement).value).toBe("2030-01-02T11:00");
    expect((screen.getByLabelText("Purpose") as HTMLTextAreaElement).value).toBe("Career guidance talk");
    expect((screen.getByLabelText("Location") as HTMLInputElement).value).toBe("Main block");
    fireEvent.click(screen.getByRole("button", { name: "Accept and book" }));
    await waitFor(() => expect(router.push).toHaveBeenCalledWith("/bdm/appointments/a9?created=1"));
    const post = fetch.mock.calls.find(([, init]) => init?.method === "POST");
    expect(post?.[0]).toBe("/api/v1/bdm/meeting-requests/r1/accept");
    expect(JSON.parse(String(post?.[1]?.body))).toMatchObject({ organization_id: "o1", contact_id: "c1", appointment_type: "school_meeting", starts_at: "2030-01-02T11:00:00+05:30" });
  });

  it("leaves the time empty when the proposed time has passed (the BDM picks a new one)", () => {
    render(<MeetingRequestDecide request={request({ proposed_at: "2020-01-01T05:30:00+00:00" })} bdmType="school" initialOrganization={null} />);
    expect((screen.getByLabelText("Date and time (IST) (required)") as HTMLInputElement).value).toBe("");
    expect(screen.getByText(/proposed time has passed/)).toBeTruthy();
  });

  it("needs a reason to decline, then refreshes the page", async () => {
    const fetch = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(() => Promise.resolve(res(request({ status: "declined" }))));
    vi.stubGlobal("fetch", fetch);
    render(<MeetingRequestDecide request={request()} bdmType="school" initialOrganization={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Decline request" }));
    expect(screen.getByText("Enter the reason for declining.")).toBeTruthy();
    expect(fetch).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Reason for declining"), { target: { value: "Out of my territory" } });
    fireEvent.click(screen.getByRole("button", { name: "Decline request" }));
    await waitFor(() => expect(router.refresh).toHaveBeenCalled());
    expect(fetch.mock.calls[0][0]).toBe("/api/v1/bdm/meeting-requests/r1/decline");
    expect(JSON.parse(String(fetch.mock.calls[0][1]?.body))).toEqual({ reason: "Out of my territory" });
  });

  it("shows the API's refusal on a decline (e.g. someone else took it)", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "This request is already accepted" }, 409))));
    render(<MeetingRequestDecide request={request()} bdmType="school" initialOrganization={null} />);
    fireEvent.change(screen.getByLabelText("Reason for declining"), { target: { value: "No" } });
    fireEvent.click(screen.getByRole("button", { name: "Decline request" }));
    expect(await screen.findByText("This request is already accepted")).toBeTruthy();
    expect(router.refresh).not.toHaveBeenCalled();
  });

  it("offers nothing when the caller may not decide", () => {
    const { container } = render(
      <MeetingRequestDecide request={request({ permissions: { can_accept: false, can_decline: false } })} bdmType="school" initialOrganization={null} />);
    expect(container.textContent).toBe("");
  });
});
