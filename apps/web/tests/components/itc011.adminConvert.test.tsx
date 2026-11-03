import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AdminLeadManagementPanel from "@/components/AdminLeadManagementPanel";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }), usePathname: () => "/it/admin/leads", useSearchParams: () => new URLSearchParams() }));

// itc-011: the IT Admin converts a Qualified IT lead from the leads table; the form opens in its own row.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const row = (id: string, over: Record<string, unknown> = {}) => ({
  id, lead_code: `LD-${id}`, name: `Lead ${id}`, email: `${id}@example.com`, phone: null, division: "it", subject: "Python", status: "qualified", source: "website",
  crm_sync_status: "sent", priority: "warm", created_at: "2026-10-06T05:00:00Z", stage_changed_at: "2026-10-06T05:00:00Z", product: null, campaign: null,
  telecaller: null, counselor: null, organization: null, bdm: null, converted_user: null, ...over,
});
const options = { prefill: { full_name: "Lead q1", email: "q1@example.com", phone: null, fee: null, recommended_program_id: null, recommended_course: null },
  batches: [{ id: "B1", name: "PY-DEC", program_id: "P1", program: "Python", fee: 45000, start_date: "2026-12-15", end_date: "2027-03-15", schedule: "Mon-Fri",
    mode: null, available: 3, recommended: false }], checklist: ["Attend the batch orientation"] };

let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (url.startsWith("/api/v1/admin/leads?")) return Promise.resolve(res({ items: [row("q1"), row("n1", { status: "new" }), row("o1", { division: "overseas" })], total: 3, limit: 50, offset: 0 }));
    if (url === "/api/v1/admin/leads/q1/convert-it" && !init?.method) return Promise.resolve(res(options));
    if (url === "/api/v1/admin/leads/q1/convert-it" && init?.method === "POST") {
      return Promise.resolve(res({ student: { id: "S1", full_name: "Lead q1", email: "q1@example.com", student_code: "ST1", setup: "pending_setup" },
        enrollment: { id: "E1", enrollment_code: "EDU-1", status: "pending_consent", course: "Python", batch: "PY-DEC" }, fee_account: {}, checklist: [],
        replayed: false, email_status: "sent", lead: row("q1", { status: "application_enrollment", converted_user: { id: "S1", full_name: "Lead q1", email: "q1@example.com" } }) }, 201));
    }
    return Promise.resolve(res({ items: [], total: 0, limit: 50, offset: 0 }));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AdminLeadManagementPanel IT conversion", () => {
  it("offers the conversion on a convertible IT lead only, to the IT Admin", async () => {
    render(<AdminLeadManagementPanel canConvertIt />);
    expect(await screen.findByRole("button", { name: "Convert Lead q1 to an IT student" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Convert Lead n1 to an IT student" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Convert Lead o1 to an IT student" })).not.toBeInTheDocument();
  });

  it("hides it from other admins", async () => {
    render(<AdminLeadManagementPanel />);
    await screen.findByText("Lead q1");
    expect(screen.queryByRole("button", { name: "Convert Lead q1 to an IT student" })).not.toBeInTheDocument();
  });

  it("converts and shows the outcome on the row", async () => {
    render(<AdminLeadManagementPanel canConvertIt />);
    fireEvent.click(await screen.findByRole("button", { name: "Convert Lead q1 to an IT student" }));
    expect(await screen.findByLabelText("Batch")).toHaveValue("B1");
    expect(screen.getByLabelText("Fee (INR)")).toHaveValue(45000);
    fireEvent.click(screen.getByRole("button", { name: "Convert and enrol" }));
    expect(await screen.findByText(/Converted: Lead q1 is enrolled in PY-DEC \(EDU-1\)\. A set-password link was emailed\./)).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByLabelText("Batch")).not.toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Convert Lead q1 to an IT student" })).not.toBeInTheDocument();
  });

  it("closes the form on Cancel", async () => {
    render(<AdminLeadManagementPanel canConvertIt />);
    fireEvent.click(await screen.findByRole("button", { name: "Convert Lead q1 to an IT student" }));
    fireEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    expect(screen.queryByLabelText("Batch")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Convert Lead q1 to an IT student" })).toBeInTheDocument();
  });
});
