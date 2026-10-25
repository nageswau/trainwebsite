import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ApplicationEnrollmentPanel from "@/components/ApplicationEnrollmentPanel";

// ccrm-027 (DEC-SCOPE-262): the counselor confirms enrolment with the confirmation document and the pre-enrolment checklist.
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (body: unknown, ok = true, status = 200) => Promise.resolve({ ok, status, json: async () => body });
const VIEW = {
  status: "offer", confirmed: false, confirmed_at: null, can_confirm: true, enrollment_date: null, university_student_id: null,
  course_start_date: "2027-09-15", pre_enrollment_checklist_complete: false, document: null,
};
const OPEN = { enrollment: VIEW, documents: [{ id: "d1", name: "cas.pdf" }] };
const ENROLL = "/api/v1/workflows/overseas/applications/a1/enrollment";

describe("ApplicationEnrollmentPanel", () => {
  it("shows loading, then a load failure with a retry, then the not-confirmed state", async () => {
    const fetchMock = vi.fn().mockReturnValueOnce(json({ detail: "Application not found" }, false, 404)).mockReturnValue(json(OPEN));
    vi.stubGlobal("fetch", fetchMock);
    render(<ApplicationEnrollmentPanel applicationId="a1" onChanged={vi.fn()} />);
    expect(screen.getByText("Loading enrolment…")).toBeInTheDocument();
    expect(await screen.findByText("Application not found")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Enrolment not confirmed yet.")).toBeInTheDocument();
  });

  it("asks for the document and the checklist, then confirms after an explicit step", async () => {
    const onChanged = vi.fn();
    const fetchMock = vi.fn((_url: string, init?: RequestInit) => (init?.method === "PUT" ? json({ changed: true, status: "enrolled", enrollment: VIEW }) : json(OPEN)));
    vi.stubGlobal("fetch", fetchMock);
    render(<ApplicationEnrollmentPanel applicationId="a1" onChanged={onChanged} />);
    fireEvent.click(await screen.findByRole("button", { name: "Confirm enrolment" }));
    expect(screen.getByLabelText("Course start date")).toHaveValue("2027-09-15");
    fireEvent.change(screen.getByLabelText("Enrolment date"), { target: { value: "2027-09-10" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByText("Attach the enrolment confirmation: pick an uploaded one or upload the file.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Confirmation document"), { target: { value: "d1" } });
    fireEvent.click(screen.getByLabelText("The pre-enrolment checklist is complete"));
    fireEvent.change(screen.getByLabelText("University student number (optional)"), { target: { value: "U-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    fireEvent.click(await screen.findByRole("button", { name: "Yes, confirm enrolment" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Enrolment confirmed."));
    const put = fetchMock.mock.calls.find(([url, init]) => url === ENROLL && init?.method === "PUT");
    expect(JSON.parse(String(put?.[1]?.body))).toEqual({
      expected_status: "offer", enrollment_date: "2027-09-10", enrollment_document_id: "d1", pre_enrollment_checklist_complete: true,
      university_student_id: "U-1", course_start_date: "2027-09-15", notes: null,
    });
  });

  it("shows a refusal from the server and keeps the entry", async () => {
    const fetchMock = vi.fn((_url: string, init?: RequestInit) =>
      init?.method === "PUT" ? json({ detail: "An offer is needed before enrollment" }, false, 422) : json(OPEN),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<ApplicationEnrollmentPanel applicationId="a1" onChanged={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Confirm enrolment" }));
    fireEvent.change(screen.getByLabelText("Enrolment date"), { target: { value: "2027-09-10" } });
    fireEvent.change(screen.getByLabelText("Confirmation document"), { target: { value: "d1" } });
    fireEvent.click(screen.getByLabelText("The pre-enrolment checklist is complete"));
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    fireEvent.click(await screen.findByRole("button", { name: "Yes, confirm enrolment" }));
    expect(await screen.findByText("An offer is needed before enrollment")).toBeInTheDocument();
    expect(screen.getByLabelText("Enrolment date")).toHaveValue("2027-09-10");
  });

  it("shows a confirmed enrolment and edits it without the confirm step", async () => {
    const confirmed = { ...VIEW, status: "enrolled", confirmed: true, confirmed_at: "2027-09-10T10:00:00Z", enrollment_date: "2027-09-10", university_student_id: "U-1", pre_enrollment_checklist_complete: true, document: { id: "d1", name: "cas.pdf" } };
    const onChanged = vi.fn();
    const fetchMock = vi.fn((_url: string, init?: RequestInit) => (init?.method === "PUT" ? json({ changed: true, enrollment: confirmed }) : json({ enrollment: confirmed, documents: OPEN.documents })));
    vi.stubGlobal("fetch", fetchMock);
    render(<ApplicationEnrollmentPanel applicationId="a1" onChanged={onChanged} />);
    expect(await screen.findByText("U-1")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Edit enrolment details" }));
    fireEvent.change(screen.getByLabelText("University student number (optional)"), { target: { value: "U-2" } });
    fireEvent.click(screen.getByRole("button", { name: "Save enrolment details" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Enrolment details saved."));
  });
});
