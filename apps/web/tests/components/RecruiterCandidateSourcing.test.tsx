import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterCandidateSourcing from "@/components/RecruiterCandidateSourcing";
import type { CandidateSourcing } from "@/lib/candidateSourcing";

// pob-018 (DEC-SCOPE-428): the Source and outreach card -- source, date, referrer, vendor, institution, portal reference, last verified,
// the outreach status and the permission to be represented; Verify details, Update outreach and Edit source details for writers.
const sourcing: CandidateSourcing = {
  source_date: "2026-03-01", referrer_name: "Kiran", referrer: { id: "c9", candidate_code: "CAN-000009", name: "Meena" },
  vendor: { id: "v1", name: "TalentBridge" }, institution: null, portal_import_reference: "Naukri #44", last_verified_on: null,
  last_verified_by: null, outreach_status: "contacted", outreach_status_changed_at: null, permission: null, permitted: false,
};
const candidate = { id: "c1", source: { id: "s1", name: "Referral", active: true }, source_detail: "Alumni group", sourcing };
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn(() => Promise.resolve(res({ id: "c1", sourcing: { ...sourcing, last_verified_on: "2026-11-08" } })));
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const sent = (method: string) => fetchMock.mock.calls.find(([, init]) => init?.method === method)!;

describe("RecruiterCandidateSourcing", () => {
  it("shows the attribution, and that the candidate cannot be put forward yet", () => {
    render(<RecruiterCandidateSourcing candidate={candidate} canEdit onSaved={vi.fn()} />);
    expect(screen.getByRole("heading", { name: "Source and outreach" })).toBeInTheDocument();
    expect(screen.getByText("Referral")).toBeInTheDocument();
    expect(screen.getByText("Alumni group")).toBeInTheDocument();
    expect(screen.getByText(/Kiran/)).toBeInTheDocument();
    expect(screen.getByText(/Meena \(CAN-000009\)/)).toBeInTheDocument();
    expect(screen.getByText("TalentBridge")).toBeInTheDocument();
    expect(screen.getByText("Naukri #44")).toBeInTheDocument();
    expect(screen.getByText("Not verified yet")).toBeInTheDocument();
    expect(screen.getByText("Contacted")).toBeInTheDocument();
    expect(screen.getByText(/No permission recorded/)).toBeInTheDocument();
  });

  it("offers no actions to a reader", () => {
    render(<RecruiterCandidateSourcing candidate={candidate} canEdit={false} onSaved={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "Verify details" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Update outreach" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Edit source details" })).toBeNull();
  });

  it("verifies the details", async () => {
    const onSaved = vi.fn();
    render(<RecruiterCandidateSourcing candidate={candidate} canEdit onSaved={onSaved} />);
    fireEvent.click(screen.getByRole("button", { name: "Verify details" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(sent("POST")[0]).toBe("/api/v1/recruiter/candidates/c1/verify");
    expect(await screen.findByText("Details verified.")).toBeInTheDocument();
  });

  it("records a permission with consented, and asks for the method first", async () => {
    const onSaved = vi.fn();
    render(<RecruiterCandidateSourcing candidate={candidate} canEdit onSaved={onSaved} />);
    fireEvent.click(screen.getByRole("button", { name: "Update outreach" }));
    fireEvent.change(screen.getByLabelText("Outreach status"), { target: { value: "consented" } });
    fireEvent.click(screen.getByRole("button", { name: "Save outreach" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Choose how the candidate agreed");
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("How they agreed"), { target: { value: "call" } });
    fireEvent.change(screen.getByLabelText("Date they agreed"), { target: { value: "2026-11-01" } });
    fireEvent.change(screen.getByLabelText("Note (optional)"), { target: { value: "On the phone" } });
    fireEvent.click(screen.getByRole("button", { name: "Save outreach" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const put = sent("PUT");
    expect(put[0]).toBe("/api/v1/recruiter/candidates/c1/outreach");
    expect(JSON.parse(put[1].body)).toEqual({ status: "consented", method: "call", given_on: "2026-11-01", note: "On the phone" });
  });

  it("sends only the status when it is not consented", async () => {
    render(<RecruiterCandidateSourcing candidate={candidate} canEdit onSaved={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Update outreach" }));
    fireEvent.change(screen.getByLabelText("Outreach status"), { target: { value: "declined" } });
    expect(screen.queryByLabelText("How they agreed")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Save outreach" }));
    await waitFor(() => expect(sent("PUT")).toBeTruthy());
    expect(JSON.parse(sent("PUT")[1].body)).toEqual({ status: "declined" });
  });

  it("shows a recorded permission", () => {
    const permitted = { ...sourcing, outreach_status: "consented" as const, permitted: true,
      permission: { method: "email", given_on: "2026-10-02", note: "Replied yes", recorded_by: { id: "u1", full_name: "Asha" } } };
    render(<RecruiterCandidateSourcing candidate={{ ...candidate, sourcing: permitted }} canEdit onSaved={vi.fn()} />);
    expect(screen.getByText(/Email/)).toBeInTheDocument();
    expect(screen.getByText(/Replied yes/)).toBeInTheDocument();
    expect(screen.getByText(/recorded by Asha/)).toBeInTheDocument();
  });

  it("edits the source details through the candidate PATCH and shows the API's error", async () => {
    fetchMock.mockImplementationOnce(() => Promise.resolve(res({ detail: "Source date cannot be in the future" }, 422)));
    render(<RecruiterCandidateSourcing candidate={candidate} canEdit onSaved={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit source details" }));
    fireEvent.change(screen.getByLabelText("Source date"), { target: { value: "2026-02-02" } });
    fireEvent.change(screen.getByLabelText("Referrer name"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save source details" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Source date cannot be in the future");
    const patch = sent("PATCH");
    expect(patch[0]).toBe("/api/v1/recruiter/candidates/c1");
    expect(JSON.parse(patch[1].body)).toEqual({ source_date: "2026-02-02", referrer_name: null });
  });
});
