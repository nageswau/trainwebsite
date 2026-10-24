import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CounselorVisaCaseForm, { type VisaCaseView } from "@/components/CounselorVisaCaseForm";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const CASE: VisaCaseView = {
  id: "v1",
  visa_status: "submitted",
  readiness_review_date: null,
  visa_category: "Student",
  appointment_date: "2026-11-01",
  appointment_place: null,
  submission_date: "2026-11-02",
  tracking_reference: null,
  interview_date: null,
  expected_decision_date: null,
  decision_date: null,
  outcome_document_id: null,
  refusal_reason: null,
  next_steps: null,
  documents: [{ id: "d1", document_type: "Visa refusal letter", original_filename: "refusal.pdf" }],
};
const respond = (status: number, body: unknown) => vi.fn(() => Promise.resolve({ ok: status < 400, status, json: async () => body }));

// ccrm-026 (DEC-SCOPE-254): the counselor's visa lifecycle form.
describe("CounselorVisaCaseForm", () => {
  it("sends only the changed fields with the shown status, and announces the save", async () => {
    const fetchMock = respond(200, { id: "v1" });
    vi.stubGlobal("fetch", fetchMock);
    const onSaved = vi.fn();
    render(<CounselorVisaCaseForm visa={CASE} onSaved={onSaved} />);
    fireEvent.change(screen.getByLabelText("Visa application reference"), { target: { value: "GWF0123" } });
    fireEvent.click(screen.getByRole("button", { name: "Save visa case" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Visa details saved.");
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/workflows/overseas/visa/v1/lifecycle");
    expect(JSON.parse(String(init.body))).toEqual({ expected_visa_status: "submitted", tracking_reference: "GWF0123" });
    expect(onSaved).toHaveBeenCalled();
  });

  it("asks for the restricted refusal reason and the evidence only when recording a refusal", async () => {
    const fetchMock = respond(200, { id: "v1" });
    vi.stubGlobal("fetch", fetchMock);
    render(<CounselorVisaCaseForm visa={CASE} onSaved={vi.fn()} />);
    expect(screen.queryByLabelText(/Refusal reason/)).toBeNull();
    fireEvent.change(screen.getByLabelText("Next status"), { target: { value: "approved" } });
    expect(screen.getByLabelText("Outcome evidence")).toBeInTheDocument();
    expect(screen.queryByLabelText(/Refusal reason/)).toBeNull();
    fireEvent.change(screen.getByLabelText("Next status"), { target: { value: "refused" } });
    fireEvent.change(screen.getByLabelText(/Refusal reason/), { target: { value: "Funds" } });
    fireEvent.change(screen.getByLabelText("Outcome evidence"), { target: { value: "d1" } });
    fireEvent.click(screen.getByRole("button", { name: "Record decision" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Visa status set to Refused.");
    const body = JSON.parse(String((fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].body));
    expect(body).toEqual({ expected_visa_status: "submitted", visa_status: "refused", refusal_reason: "Funds", outcome_document_id: "d1" });
  });

  it("puts a 422 on its field and keeps the entry", async () => {
    vi.stubGlobal("fetch", respond(422, { detail: [{ loc: ["body", "expected_decision_date"], msg: "Value error, The expected decision date cannot be before the submission date" }] }));
    render(<CounselorVisaCaseForm visa={CASE} onSaved={vi.fn()} />);
    const field = screen.getByLabelText("Expected decision date");
    fireEvent.change(field, { target: { value: "2026-10-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Save visa case" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The expected decision date cannot be before the submission date");
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(field).toHaveValue("2026-10-01");
  });

  it("reloads the case on a stale-screen 409, keeping the message", async () => {  // browser QA-03
    vi.stubGlobal("fetch", respond(409, { detail: "This visa case changed since you opened it -- reload to see its current stage" }));
    const onSaved = vi.fn();
    render(<CounselorVisaCaseForm visa={CASE} onSaved={onSaved} />);
    fireEvent.change(screen.getByLabelText("Visa category"), { target: { value: "Work" } });
    fireEvent.click(screen.getByRole("button", { name: "Save visa case" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("changed since you opened it");
    expect(onSaved).toHaveBeenCalled();
  });

  it("is read-only once the decision is recorded", () => {
    render(<CounselorVisaCaseForm visa={{ ...CASE, visa_status: "approved" }} onSaved={vi.fn()} />);
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText(/Ask the Overseas Admin to correct it/)).toBeInTheDocument();
  });
});
