import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CandidateDataRequestQueue from "@/components/CandidateDataRequestQueue";
import CandidatePrivacyPanel from "@/components/CandidatePrivacyPanel";
import CandidateRetentionCard from "@/components/CandidateRetentionCard";
import type { DataRequestRow, Retention } from "@/lib/candidateDataRequests";
import type { PrivacyState } from "@/lib/candidatePortal";

// hrc-035 (DEC-SCOPE-396): the candidate's "Delete my data" (K6), the HR Manager's queue (K5/K7) and the retention rule (K8).
const json = (status: number, body: unknown) => Promise.resolve({ ok: status < 400, status, json: async () => body, headers: new Headers() });
let fetchMock: ReturnType<typeof vi.fn>;
const PRIVACY: PrivacyState = { opted_in: true, consent: { version: "candidate-v1", text: "I agree." }, history: [], erasure: null };
const ROW: DataRequestRow = {
  id: "r1", status: "in_progress", requested_at: "2026-11-04T10:00:00Z", decided_at: null, rejection_reason: null,
  candidate: { id: "c1", candidate_code: "CAN-000001", name: "Asha Verma", email: "asha@example.com", anonymised: false }, open_applications: 0, held: false,
};
const RETENTION: Retention = { months: null, range: [6, 120], due_now: 0, last_run_at: null, last_run_count: null, can_edit: true };

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Delete my data (candidate Privacy)", () => {
  it("asks for confirmation, sends one request and shows it waiting", async () => {
    fetchMock.mockReturnValue(json(201, { ...PRIVACY, erasure: { status: "in_progress", requested_at: "2026-11-04T10:00:00Z", decided_at: null, rejection_reason: null } }));
    render(<CandidatePrivacyPanel initial={PRIVACY} />);
    fireEvent.click(screen.getByRole("button", { name: "Request deletion" }));
    const send = screen.getByRole("button", { name: "Send deletion request" });
    expect(send).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(send);
    expect(await screen.findByText(/is waiting for review/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/candidate/me/erasure-request");
    expect(screen.queryByRole("button", { name: "Request deletion" })).not.toBeInTheDocument();
  });

  it("shows a declined request's reason and lets the candidate ask again; cancel sends nothing", () => {
    const declined = { status: "rejected" as const, requested_at: "2026-11-01T10:00:00Z", decided_at: "2026-11-02T10:00:00Z", rejection_reason: "A placement contract needs it" };
    render(<CandidatePrivacyPanel initial={{ ...PRIVACY, erasure: declined }} />);
    expect(screen.getByText(/was declined: A placement contract needs it/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Request deletion" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("button", { name: "Request deletion" })).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows a server failure as an alert", async () => {
    fetchMock.mockReturnValue(json(500, { detail: "boom" }));
    render(<CandidatePrivacyPanel initial={PRIVACY} />);
    fireEvent.click(screen.getByRole("button", { name: "Request deletion" }));
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Send deletion request" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("We couldn't send your request");
  });
});

describe("CandidateDataRequestQueue", () => {
  it("shows the empty state", () => {
    render(<CandidateDataRequestQueue open={[]} decided={[]} />);
    expect(screen.getByText("No deletion requests waiting.")).toBeInTheDocument();
  });

  it("needs a reason to decline and moves the decided request down", async () => {
    fetchMock.mockReturnValue(json(200, { ...ROW, status: "rejected", decided_at: "2026-11-04T11:00:00Z", rejection_reason: "Needed for a contract" }));
    render(<CandidateDataRequestQueue open={[ROW]} decided={[]} />);
    fireEvent.click(screen.getByRole("button", { name: "Decline…" }));
    fireEvent.click(screen.getByRole("button", { name: "Decline the request" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Give the candidate a reason");
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Reason shown to the candidate"), { target: { value: "Needed for a contract" } });
    fireEvent.click(screen.getByRole("button", { name: "Decline the request" }));
    expect(await screen.findByText("Asha Verma (CAN-000001)'s request was declined.")).toBeInTheDocument();
    expect(JSON.parse(String(fetchMock.mock.calls[0][1].body))).toEqual({ decision: "reject", reason: "Needed for a contract" });
    expect(screen.getByText("No deletion requests waiting.")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Decided" })).getByText(/Needed for a contract/)).toBeInTheDocument();
  });

  it("confirms an approval, and a held request cannot be approved", async () => {
    fetchMock.mockReturnValue(json(200, { ...ROW, status: "fulfilled", decided_at: "2026-11-04T11:00:00Z" }));
    render(<CandidateDataRequestQueue open={[ROW, { ...ROW, id: "r2", held: true, open_applications: 1 }]} decided={[]} />);
    const [first, second] = screen.getAllByRole("listitem");
    expect(within(second).getByText(/On hold/)).toBeInTheDocument();
    expect(within(second).getByRole("button", { name: "Approve deletion" })).toBeDisabled();
    fireEvent.click(within(first).getByRole("button", { name: "Approve deletion" }));
    fireEvent.click(within(first).getByRole("button", { name: "Delete the data" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("data was deleted"));
    expect(JSON.parse(String(fetchMock.mock.calls[0][1].body))).toEqual({ decision: "approve" });
  });

  it("shows the server's refusal", async () => {
    fetchMock.mockReturnValue(json(409, { detail: "This request has already been decided" }));
    render(<CandidateDataRequestQueue open={[ROW]} decided={[]} />);
    fireEvent.click(screen.getByRole("button", { name: "Approve deletion" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete the data" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("already been decided");
  });
});

describe("CandidateRetentionCard", () => {
  it("is off by default, checks the range and saves a period", async () => {
    fetchMock.mockReturnValue(json(200, { ...RETENTION, months: 24, due_now: 3 }));
    render(<CandidateRetentionCard initial={RETENTION} />);
    expect(screen.getByText("Off")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Months after the last activity"), { target: { value: "3" } });
    fireEvent.click(screen.getByRole("button", { name: "Save rule" }));
    expect(screen.getByRole("alert")).toHaveTextContent("from 6 to 120");
    fireEvent.change(screen.getByLabelText("Months after the last activity"), { target: { value: "24" } });
    fireEvent.click(screen.getByRole("button", { name: "Save rule" }));
    expect(await screen.findByText(/anonymised after 24 months/)).toBeInTheDocument();
    expect(JSON.parse(String(fetchMock.mock.calls[0][1].body))).toEqual({ months: 24 });
    expect(screen.getByText(/3 candidates are due now/)).toBeInTheDocument();
  });

  it("is read-only for the HR Manager", () => {
    render(<CandidateRetentionCard initial={{ ...RETENTION, can_edit: false }} />);
    expect(screen.queryByRole("button", { name: "Save rule" })).not.toBeInTheDocument();
    expect(screen.getByText("Only a super admin can change this rule.")).toBeInTheDocument();
  });
});
