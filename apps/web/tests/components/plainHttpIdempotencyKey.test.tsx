import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import DataPrivacyPanel from "@/components/DataPrivacyPanel";
import FeePaymentPanel from "@/components/FeePaymentPanel";
import SchoolBulkEntryPanel from "@/components/SchoolBulkEntryPanel";
import SchoolBulkUploadPanel from "@/components/SchoolBulkUploadPanel";
import { BULK_RESULTS } from "@/lib/bulkEntry";

// QA-029-01, same defect in the other Idempotency-Key senders: on a plain-HTTP page (reached by IP or hostname) the browser has
// `crypto.getRandomValues` but no `crypto.randomUUID`. Each action must still send its request with a well-formed key.
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

function keyOfCall(fetchMock: ReturnType<typeof vi.fn>, path: string): string | undefined {
  const call = fetchMock.mock.calls.find(([url, init]) => String(url).includes(path) && (init as RequestInit | undefined)?.method === "POST");
  return call ? ((call[1] as RequestInit).headers as Record<string, string>)["Idempotency-Key"] : undefined;
}

const realCrypto = globalThis.crypto; // captured before stubbing, so the stub never calls itself

beforeEach(() => {
  vi.stubGlobal("crypto", { getRandomValues: (a: Uint8Array) => realCrypto.getRandomValues(a) });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Idempotency-Key senders work without crypto.randomUUID", () => {
  it("ENH-028 bulk entry panel", async () => {
    const fetchMock = vi.fn(async () => json({ id: "b", total_rows: 0, accepted_count: 0, rejected_count: 0, rows: [] }, 201));
    vi.stubGlobal("fetch", fetchMock);
    render(<SchoolBulkEntryPanel target={BULK_RESULTS} hasStudents />);
    fireEvent.click(screen.getByText(BULK_RESULTS.title));
    fireEvent.change(screen.getByLabelText(/Filled-in results file/), { target: { files: [new File(["student_code\n"], "m.csv", { type: "text/csv" })] } });
    fireEvent.click(screen.getByRole("button", { name: "Upload results" }));
    await waitFor(() => expect(keyOfCall(fetchMock, "/bulk-upload")).toMatch(UUID_V4));
  });

  it("roster bulk upload panel", async () => {
    const fetchMock = vi.fn(async () => json({ id: "b", status: "completed", total_rows: 0, accepted_count: 0, rejected_count: 0, rows: [] }, 201));
    vi.stubGlobal("fetch", fetchMock);
    render(<SchoolBulkUploadPanel />);
    fireEvent.change(screen.getByLabelText("Filled-in roster file"), { target: { files: [new File(["full_name\nA\n"], "r.csv", { type: "text/csv" })] } });
    fireEvent.submit(screen.getByLabelText("Filled-in roster file").closest("form")!);
    await waitFor(() => expect(keyOfCall(fetchMock, "/students/bulk-upload")).toMatch(UUID_V4));
  });

  it("fee payment Pay Now", async () => {
    const row = { id: "p1", amount: 100, currency: "INR", provider: "razorpay", status: "pending", due_date: null, reference_type: "course", is_manual: false, emi_schedule_id: null, installment_no: null };
    const fetchMock = vi.fn(async (url: string) => {
      if (url.endsWith("/payments/mine")) return json([row]);
      if (url.endsWith("/payments/emi-schedule")) return json([]);
      return json({ status: "configuration_required" });
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<FeePaymentPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Pay Now" }));
    await waitFor(() => expect(keyOfCall(fetchMock, "/payments/p1/checkout")).toMatch(UUID_V4));
  });

  it("data privacy request", async () => {
    const fetchMock = vi.fn(async () => json({ id: "r1", type: "delete", status: "in_progress", rejection_reason: null }, 201));
    vi.stubGlobal("fetch", fetchMock);
    render(<DataPrivacyPanel />);
    fireEvent.click(screen.getByRole("button", { name: "Request account deletion" }));
    await waitFor(() => expect(keyOfCall(fetchMock, "/account/data-requests")).toMatch(UUID_V4));
  });
});
