import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmAppointmentForm from "@/components/BdmAppointmentForm";
import type { Appointment } from "@/lib/bdmAppointments";
import type { Organization } from "@/lib/bdmOrganizations";

const router = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const org = { id: "o1", code: "ORG-000001", name: "St Mary", contacts: [
  { id: "c1", name: "Ms Iyer", designation: null, role: null, phone: null, email: null, is_primary: false },
  { id: "c2", name: "Dr Rao", designation: "Principal", role: "principal", phone: null, email: null, is_primary: true },
] } as unknown as Organization;
const appt = (over: Partial<Appointment> = {}) => ({
  id: "a1", code: "APT-000001", starts_at: "2030-01-07T04:30:00Z", duration_minutes: 60, appointment_type: "college_meeting", status: "scheduled",
  organization: { id: "o1", code: "ORG-000001", name: "St Mary", archived: false }, contact_name: "Dr Rao", contact_id: "c2", bdm: { id: "b1", full_name: "Asha", active: true },
  contact_designation: "Principal", contact_phone: null, contact_email: null, location: "Gate 1", purpose: null, remarks: null, outcome: null, next_follow_up_on: null,
  expected_leads: null, expected_revenue: null, events: [], created_at: "", updated_at: "",
  permissions: { can_edit: true, can_confirm: true, can_reschedule: true, can_cancel: true, can_no_show: false, can_complete: false }, ...over,
}) as Appointment;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  router.push.mockClear();
});

function fillWhen(value = "2030-01-07T10:00") {
  fireEvent.change(screen.getByLabelText("Date and time (IST) (required)"), { target: { value } });
  // jsdom does enforce HTML `required` on a submit click, so the required Type must be chosen too.
  fireEvent.change(screen.getByLabelText("Type (required)"), { target: { value: "college_meeting" } });
}

describe("BdmAppointmentForm (bdm-006 §6.2, R-F6)", () => {
  it("preselects the primary contact, lists the BDM type's types, and books in IST", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(res({ appointment: appt() }, 201)));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmAppointmentForm mode="create" bdmType="college" initialOrganization={org} />);
    expect(screen.getByLabelText("Contact person (required)")).toHaveValue("c2");
    const types = Array.from((screen.getByLabelText("Type (required)") as HTMLSelectElement).options).map((o) => o.value);
    expect(types).toContain("placement_discussion");
    expect(types).not.toContain("agent_visit");
    fillWhen();
    fireEvent.click(screen.getByRole("button", { name: "Book appointment" }));
    await waitFor(() => expect(router.push).toHaveBeenCalledWith("/bdm/appointments/a1?created=1"));
    const body = JSON.parse(String((fetchMock.mock.calls[0] as unknown[])[1] && ((fetchMock.mock.calls[0] as unknown[])[1] as RequestInit).body));
    expect(body).toMatchObject({ organization_id: "o1", contact_id: "c2", starts_at: "2030-01-07T10:00:00+05:30", duration_minutes: 60, confirm_overlap: false });
    expect(body.expected_leads).toBeNull();
  });

  it("warns on overlap, then saves anyway with confirm_overlap", async () => {
    const detail = { code: "possible_overlap", message: "You already have an appointment at this time", total: 1, matches: [{ id: "x", code: "APT-000009", starts_at: "2030-01-07T04:30:00Z", duration_minutes: 60, organization_name: "Holy Cross" }] };
    const fetchMock = vi.fn().mockResolvedValueOnce(res({ detail }, 409)).mockResolvedValueOnce(res({ appointment: appt() }, 201));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmAppointmentForm mode="create" bdmType="college" initialOrganization={org} />);
    fillWhen();
    fireEvent.click(screen.getByRole("button", { name: "Book appointment" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("APT-000009");
    expect(alert).toHaveTextContent("Holy Cross");
    expect(screen.getByRole("button", { name: "Book appointment" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Save anyway" }));
    await waitFor(() => expect(router.push).toHaveBeenCalled());
    expect(JSON.parse(String(((fetchMock.mock.calls[1] as unknown[])[1] as RequestInit).body)).confirm_overlap).toBe(true);
  });

  it("clears the overlap warning when a field changes, so Save anyway cannot confirm unchecked values", async () => {
    const detail = { code: "possible_overlap", message: "You already have an appointment at this time", total: 1, matches: [{ id: "x", code: "APT-000009", starts_at: "2030-01-07T04:30:00Z", duration_minutes: 60, organization_name: "Holy Cross" }] };
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail }, 409))));
    render(<BdmAppointmentForm mode="create" bdmType="college" initialOrganization={org} />);
    fillWhen();
    fireEvent.click(screen.getByRole("button", { name: "Book appointment" }));
    await screen.findByRole("alert");
    fireEvent.change(screen.getByLabelText("Duration"), { target: { value: "30" } });
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("button", { name: "Book appointment" })).toBeEnabled();
  });

  const clash = { code: "possible_overlap", message: "You already have an appointment at this time", total: 1, matches: [{ id: "x", code: "APT-000009", starts_at: "2030-01-07T04:30:00Z", duration_minutes: 60, organization_name: "Holy Cross" }] };
  const bodyOf = (mock: ReturnType<typeof vi.fn>, call: number) => JSON.parse(String(((mock.mock.calls[call] as unknown[])[1] as RequestInit).body));

  it("Save anyway resends the exact body that was checked, even if the time was edited while the request was pending", async () => {
    let settle!: (r: Response) => void;
    const fetchMock = vi.fn().mockReturnValueOnce(new Promise<Response>((r) => { settle = r; })).mockResolvedValueOnce(res({ appointment: appt() }, 201));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmAppointmentForm mode="create" bdmType="college" initialOrganization={org} />);
    fillWhen("2030-01-07T10:00");
    fireEvent.click(screen.getByRole("button", { name: "Book appointment" }));
    fireEvent.change(screen.getByLabelText("Date and time (IST) (required)"), { target: { value: "2030-01-09T15:00" } });
    settle(res({ detail: clash }, 409));
    await screen.findByRole("button", { name: "Save anyway" });
    fireEvent.click(screen.getByRole("button", { name: "Save anyway" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(bodyOf(fetchMock, 1)).toMatchObject({ starts_at: "2030-01-07T10:00:00+05:30", confirm_overlap: true });
  });

  it("edit mode: Save anyway PATCHes the checked body with confirm_overlap, not later edits", async () => {
    let settle!: (r: Response) => void;
    let patchCalls = 0;
    const onSaved = vi.fn();
    const fetchMock = vi.fn((...args: [string, RequestInit?]) => {
      if (args[0].includes("/organizations/")) return Promise.resolve(res({ organization: org }));
      return patchCalls++ === 0 ? new Promise<Response>((r) => { settle = r; }) : Promise.resolve(res({ appointment: appt({ duration_minutes: 90 }) }));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmAppointmentForm mode="edit" bdmType="college" appointment={appt()} onSaved={onSaved} onCancel={() => {}} />);
    await waitFor(() => expect(screen.getByLabelText("Contact person (required)")).toHaveValue("c2"));
    fireEvent.change(screen.getByLabelText("Duration"), { target: { value: "90" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    fireEvent.change(screen.getByLabelText("Location"), { target: { value: "Gate 7" } });
    settle(res({ detail: clash }, 409));
    fireEvent.click(await screen.findByRole("button", { name: "Save anyway" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const patches = fetchMock.mock.calls.filter(([, init]) => init?.method === "PATCH");
    expect(patches).toHaveLength(2);
    expect(JSON.parse(String(patches[1][1]?.body))).toEqual({ duration_minutes: 90, confirm_overlap: true });
  });

  it("lets a booking whose contact was deleted be edited without choosing a contact", async () => {
    const onSaved = vi.fn();
    const fetchMock = vi.fn((...args: [string, RequestInit?]) => Promise.resolve(args[0].includes("/organizations/") ? res({ organization: org }) : res({ appointment: appt({ contact_id: null, location: "Gate 9" }) })));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmAppointmentForm mode="edit" bdmType="college" appointment={appt({ contact_id: null })} onSaved={onSaved} onCancel={() => {}} />);
    await screen.findByText(/was removed/);
    expect(screen.getByLabelText("Contact person")).not.toBeRequired();
    fireEvent.change(screen.getByLabelText("Location"), { target: { value: "Gate 9" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(expect.objectContaining({ location: "Gate 9" }), true));
    const patches = fetchMock.mock.calls.filter(([, init]) => init?.method === "PATCH");
    expect(patches).toHaveLength(1);
    expect(JSON.parse(String(patches[0][1]?.body))).toEqual({ location: "Gate 9" });
  });

  it("keeps the entry and shows the API message on failure", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "This organization is archived — restore it before booking" }, 422))));
    render(<BdmAppointmentForm mode="create" bdmType="college" initialOrganization={org} />);
    fillWhen();
    fireEvent.change(screen.getByLabelText("Location"), { target: { value: "Main block" } });
    fireEvent.click(screen.getByRole("button", { name: "Book appointment" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("archived");
    expect(screen.getByLabelText("Location")).toHaveValue("Main block");
  });

  it("edit sends only changed fields and reports no-change", async () => {
    const onSaved = vi.fn();
    const fetchMock = vi.fn((...args: [string, RequestInit?]) => Promise.resolve(args[0].includes("/organizations/") ? res({ organization: org }) : res({ appointment: appt({ location: "Gate 2" }) })));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmAppointmentForm mode="edit" bdmType="college" appointment={appt()} onSaved={onSaved} onCancel={() => {}} />);
    await waitFor(() => expect(screen.getByLabelText("Contact person (required)")).toHaveValue("c2"));
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(expect.objectContaining({ id: "a1" }), false));
    fireEvent.change(screen.getByLabelText("Location"), { target: { value: "Gate 2" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(onSaved).toHaveBeenLastCalledWith(expect.objectContaining({ location: "Gate 2" }), true));
    const patch = fetchMock.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === "PATCH");
    expect(JSON.parse(String((patch![1] as RequestInit).body))).toEqual({ location: "Gate 2" });
  });

  it("asks for a new contact when the booked one was deleted", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ organization: org }))));
    render(<BdmAppointmentForm mode="edit" bdmType="college" appointment={appt({ contact_id: null })} onSaved={() => {}} onCancel={() => {}} />);
    expect(await screen.findByText(/The booked contact \(Dr Rao\) was removed/)).toBeInTheDocument();
  });
});
