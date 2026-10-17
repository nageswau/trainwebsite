import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentRegistrationStatus from "@/components/AgentRegistrationStatus";

const { replace } = vi.hoisted(() => ({ replace: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace, refresh: vi.fn(), push: vi.fn() }) }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.clearAllMocks(); });

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const doc = (doc_type: string, label: string, status: string, extra = {}) => ({ id: `${doc_type}-id`, doc_type, label, status, rejection_reason: null, original_filename: "f.pdf", content_type: "application/pdf", file_size: 10, updated_at: "2026-10-17T00:00:00Z", doc_number_display: "ABCDE****F", ...extra });
const pending = (docs: unknown[]) => ({ org: { name: "ABC Overseas", status: "pending", kyc_required: true }, documents: docs });
const pdf = () => new File([new Uint8Array(10)], "a.pdf", { type: "application/pdf" });

describe("AgentRegistrationStatus (AGN-024)", () => {
  it("shows each document's status and the rejection reason, with re-upload only for rejected", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(pending([doc("pan", "PAN card", "verified"), doc("aadhaar", "Aadhaar card", "rejected", { rejection_reason: "Blurred", doc_number_display: "XXXX XXXX 1234" }), doc("business_license", "Business licence", "pending")]))));
    render(<AgentRegistrationStatus />);
    expect(await screen.findByText("Reason: Blurred")).toBeInTheDocument();
    expect(screen.getByText("Verified")).toBeInTheDocument();
    expect(screen.getByLabelText(/^New Aadhaar card file/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/^New PAN card file/)).toBeNull();
  });

  it("re-uploads a rejected document as multipart PUT", async () => {
    const mock = vi.fn((url: string, init?: RequestInit) => Promise.resolve(init?.method === "PUT" ? json(doc("aadhaar", "Aadhaar card", "pending")) : json(pending([doc("aadhaar", "Aadhaar card", "rejected", { rejection_reason: "Blurred" })]))));
    vi.stubGlobal("fetch", mock);
    render(<AgentRegistrationStatus />);
    fireEvent.change(await screen.findByLabelText(/^New Aadhaar card file/), { target: { files: [pdf()] } });
    fireEvent.submit(screen.getByRole("button", { name: "Upload new Aadhaar card" }).closest("form")!);
    await waitFor(() => expect(mock.mock.calls.some(([u, i]) => String(u).endsWith("/documents/aadhaar/file") && i?.method === "PUT" && i.body instanceof FormData)).toBe(true));
    const put = mock.mock.calls.find(([, i]) => i?.method === "PUT")![1]!.body as FormData;
    expect(put.get("file")).toBeInstanceOf(File);
    expect(put.has("doc_number")).toBe(false);
  });

  it("sends a blank-file submit nowhere and reports the problem", async () => {
    const mock = vi.fn().mockResolvedValue(json(pending([doc("aadhaar", "Aadhaar card", "rejected")])));
    vi.stubGlobal("fetch", mock);
    render(<AgentRegistrationStatus />);
    await screen.findByLabelText(/^New Aadhaar card file/);
    fireEvent.submit(screen.getByRole("button", { name: "Upload new Aadhaar card" }).closest("form")!);
    expect(await screen.findByRole("alert")).toHaveTextContent("Aadhaar card: choose a file.");
    expect(mock).toHaveBeenCalledTimes(1);
  });

  it("on 409 shows the message and reloads the status", async () => {
    let gets = 0;
    const mock = vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === "PUT") return Promise.resolve(json({ detail: "Document is not rejected" }, 409));
      gets += 1;
      return Promise.resolve(json(pending([doc("aadhaar", "Aadhaar card", gets === 1 ? "rejected" : "verified")])));
    });
    vi.stubGlobal("fetch", mock);
    render(<AgentRegistrationStatus />);
    fireEvent.change(await screen.findByLabelText(/^New Aadhaar card file/), { target: { files: [pdf()] } });
    fireEvent.submit(screen.getByRole("button", { name: "Upload new Aadhaar card" }).closest("form")!);
    await waitFor(() => expect(gets).toBe(2));
    expect(await screen.findByRole("alert")).toHaveTextContent(/not rejected/i);
    expect(screen.queryByLabelText(/^New Aadhaar card file/)).toBeNull();
  });

  it("sends an active agency to the dashboard and tells a rejected one", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ org: { name: "ABC", status: "active", kyc_required: true }, documents: [] })));
    render(<AgentRegistrationStatus />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/overseas/agent/dashboard"));
    cleanup();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ org: { name: "ABC", status: "rejected", kyc_required: true }, documents: [doc("pan", "PAN card", "rejected", { rejection_reason: "Fake" })] })));
    render(<AgentRegistrationStatus />);
    expect(await screen.findByText("Registration rejected")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Upload new/ })).toBeNull();
  });
});
