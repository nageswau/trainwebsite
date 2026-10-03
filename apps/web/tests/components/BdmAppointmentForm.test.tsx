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

  it("QA6-04: a 5xx (non-JSON body) shows an actionable sentence and keeps the entry; a 422 still shows the server's detail", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response("<html>oops</html>", { status: 500 })).mockResolvedValueOnce(res({ detail: "Appointment time must be in the future" }, 422));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmAppointmentForm mode="create" bdmType="college" initialOrganization={org} />);
    fillWhen();
    fireEvent.change(screen.getByLabelText("Location"), { target: { value: "Gate 1" } });
    fireEvent.click(screen.getByRole("button", { name: "Book appointment" }));
    expect(await screen.findByText("We couldn't save the appointment. Please try again — your entry is kept.")).toBeInTheDocument();
    expect(screen.getByLabelText("Location")).toHaveValue("Gate 1");
    fireEvent.click(screen.getByRole("button", { name: "Book appointment" }));
    expect(await screen.findByText("Appointment time must be in the future")).toBeInTheDocument();
  });

  describe("QA6-05 inline validation of the estimates", () => {
    const submitForm = () => fireEvent.click(screen.getByRole("button", { name: "Book appointment" }));
    it("rejects a negative lead count without sending, with aria-invalid, a described message and focus", () => {
      const fetchMock = vi.fn();
      vi.stubGlobal("fetch", fetchMock);
      render(<BdmAppointmentForm mode="create" bdmType="college" initialOrganization={org} />);
      fillWhen();
      fireEvent.change(screen.getByLabelText("Expected leads"), { target: { value: "-3" } });
      submitForm();
      const leads = screen.getByLabelText("Expected leads");
      expect(fetchMock).not.toHaveBeenCalled();
      expect(leads).toHaveAttribute("aria-invalid", "true");
      expect(leads).toHaveValue(-3);
      expect(leads).toHaveFocus();
      expect(screen.getByText("Expected leads must be a whole number from 0.")).toHaveAttribute("id", leads.getAttribute("aria-describedby"));
      expect(leads).not.toHaveAttribute("min");
      fireEvent.change(leads, { target: { value: "3" } });
      expect(leads).not.toHaveAttribute("aria-invalid", "true");
      expect(screen.queryByText("Expected leads must be a whole number from 0.")).toBeNull();
    });
    it("rejects revenue with more than two decimals and focuses the first invalid field", () => {
      const fetchMock = vi.fn();
      vi.stubGlobal("fetch", fetchMock);
      render(<BdmAppointmentForm mode="create" bdmType="college" initialOrganization={org} />);
      fillWhen();
      fireEvent.change(screen.getByLabelText("Expected revenue (INR)"), { target: { value: "12.345" } });
      submitForm();
      const revenue = screen.getByLabelText("Expected revenue (INR)");
      expect(fetchMock).not.toHaveBeenCalled();
      expect(revenue).toHaveAttribute("aria-invalid", "true");
      expect(revenue).toHaveFocus();
      expect(screen.getByText("Expected revenue must be 0 or more, with up to 2 decimals.")).toBeInTheDocument();
    });
    it("sends valid values", async () => {
      const fetchMock = vi.fn(() => Promise.resolve(res({ appointment: appt() }, 201)));
      vi.stubGlobal("fetch", fetchMock);
      render(<BdmAppointmentForm mode="create" bdmType="college" initialOrganization={org} />);
      fillWhen();
      fireEvent.change(screen.getByLabelText("Expected leads"), { target: { value: "12" } });
      fireEvent.change(screen.getByLabelText("Expected revenue (INR)"), { target: { value: "1500.50" } });
      submitForm();
      await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
      expect(bodyOf(fetchMock as unknown as ReturnType<typeof vi.fn>, 0)).toMatchObject({ expected_leads: 12, expected_revenue: "1500.50" });
    });
    it("edit mode validates too", () => {
      const fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(res({ organization: org })));
      vi.stubGlobal("fetch", fetchMock);
      render(<BdmAppointmentForm mode="edit" bdmType="college" appointment={appt()} onSaved={() => {}} onCancel={() => {}} />);
      fireEvent.change(screen.getByLabelText("Expected leads"), { target: { value: "2000000" } });
      fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
      expect(screen.getByLabelText("Expected leads")).toHaveAttribute("aria-invalid", "true");
      expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(false);
    });
  });

  it("QA6-02: the four fieldsets use the form-section class and their labels still resolve", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<BdmAppointmentForm mode="create" bdmType="college" initialOrganization={org} />);
    for (const name of ["Who", "When", "Details", "Estimates"]) expect(screen.getByRole("group", { name })).toHaveClass("form-section");
    for (const label of ["Contact person (required)", "Date and time (IST) (required)", "Duration", "Type (required)", "Location", "Purpose", "Remarks", "Expected leads", "Expected revenue (INR)"]) {
      expect(screen.getByLabelText(label)).toBeInTheDocument();
    }
  });

  it("QA6-03: the overlap alert reuses the form-error warning style and scrolls into view with focus", async () => {
    const scroll = vi.fn();
    Element.prototype.scrollIntoView = scroll;
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(res({ detail: clash }, 409)));
    render(<BdmAppointmentForm mode="create" bdmType="college" initialOrganization={org} />);
    fillWhen();
    fireEvent.click(screen.getByRole("button", { name: "Book appointment" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveClass("form-error");
    expect(alert).not.toHaveClass("action-card");
    expect(scroll).toHaveBeenCalledWith({ block: "center" });
    expect(screen.getByRole("heading", { name: /already have an appointment/ })).toHaveFocus();
    expect(alert.nextElementSibling?.className).toContain("actions"); // adjacent to the submit actions
    delete (Element.prototype as { scrollIntoView?: unknown }).scrollIntoView;
  });
});
