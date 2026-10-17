import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentKycReview from "@/components/AgentKycReview";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const doc = (doc_type: string, label: string, status = "pending", extra = {}) => ({ id: `${doc_type}-id`, doc_type, label, status, rejection_reason: null, original_filename: `${doc_type}.pdf`, content_type: "application/pdf", file_size: 10, updated_at: "2026-10-17T00:00:00Z", doc_number: doc_type === "aadhaar" ? "1234" : "ABCDE1234F", reviewed_at: null, ...extra });
const LIST = { kyc_required: true, org_status: "pending", items: [doc("pan", "PAN card"), doc("aadhaar", "Aadhaar card"), doc("business_license", "Business licence")] };

describe("AgentKycReview (AGN-024)", () => {
  it("lists each document with number, status and a View link to the streamed file", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(LIST)));
    render(<AgentKycReview orgId="org-1" orgName="ABC" onChanged={vi.fn()} />);
    const panRow = (await screen.findByText("PAN card")).closest("li") as HTMLElement;
    expect(within(panRow).getByText("ABCDE1234F")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View PAN card for ABC" })).toHaveAttribute("href", "/api/v1/overseas-admin/agent-orgs/org-1/kyc-documents/pan-id/file");
    expect(screen.getAllByText("Pending review")).toHaveLength(3);
  });

  it("verifies a document and reports the change", async () => {
    const onChanged = vi.fn();
    const mock = vi.fn((url: string, init?: RequestInit) => Promise.resolve(init?.method === "POST" ? json(doc("pan", "PAN card", "verified")) : json(LIST)));
    vi.stubGlobal("fetch", mock);
    render(<AgentKycReview orgId="org-1" orgName="ABC" onChanged={onChanged} />);
    fireEvent.click(await screen.findByRole("button", { name: "Verify PAN card for ABC" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(screen.getByText("PAN card verified.")).toBeInTheDocument();
    expect(mock.mock.calls.some(([u, i]) => String(u).endsWith("/pan-id/verify") && i?.method === "POST")).toBe(true);
  });

  it("requires a reason to reject and sends it", async () => {
    const mock = vi.fn((url: string, init?: RequestInit) => Promise.resolve(init?.method === "POST" ? json(doc("aadhaar", "Aadhaar card", "rejected", { rejection_reason: "Blurred photo" })) : json(LIST)));
    vi.stubGlobal("fetch", mock);
    render(<AgentKycReview orgId="org-1" orgName="ABC" onChanged={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Reject Aadhaar card for ABC" }));
    const reason = screen.getByLabelText("Reason for rejecting Aadhaar card");
    expect(reason).toBeRequired();
    fireEvent.change(reason, { target: { value: "Blurred photo" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm reject" }));
    await waitFor(() => expect(mock.mock.calls.some(([u, i]) => String(u).endsWith("/aadhaar-id/reject") && JSON.parse(String(i?.body)).reason === "Blurred photo")).toBe(true));
  });
});
