import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentDocumentRequestForm from "@/components/AgentDocumentRequestForm";
import AgentDocumentRequestsPanel from "@/components/AgentDocumentRequestsPanel";
import AgentDocumentsPanel from "@/components/AgentDocumentsPanel";
import AgentDocumentUploadForm from "@/components/AgentDocumentUploadForm";
import type { User } from "@/lib/types";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }), useSearchParams: () => new URLSearchParams() }));

const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status }));
const page = (items: unknown[]) => ({ items, total: items.length, limit: 20, offset: 0 });
const agent = (role: "master" | "staff", canVerify = false) =>
  ({ id: "u1", role: "agent", division: "overseas", full_name: "A", agent_member_role: role, agent_permissions: { can_verify_documents: canVerify, can_view_reports: false } }) as unknown as User;

const DOC = {
  id: "d1",
  agent_student_id: "s1",
  student: "Asha Rao",
  has_login: false,
  document_type: "Passport",
  document_label: null,
  verification_status: "pending",
  reviewer_notes: null,
  application_id: null,
  university: null,
  original_filename: "passport.pdf",
  content_type: "application/pdf",
  file_size: 2048,
  uploaded_by: "Maya Master",
  fulfils_request_id: null,
  created_at: "2026-10-02T10:00:00Z",
  updated_at: "2026-10-02T10:00:00Z",
  replaceable: true,
};

type Handler = (url: string, init?: RequestInit) => Promise<Response> | undefined;
function stubFetch(handler: Handler) {
  const mock = vi.fn((url: string, init?: RequestInit) => handler(url, init) ?? json({}, 404));
  vi.stubGlobal("fetch", mock);
  return mock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AgentDocumentsPanel", () => {
  it("shows loading, then the documents with their status in words", async () => {
    stubFetch((url) => (url.includes("/crm/documents?") ? json(page([DOC])) : undefined));
    render(<AgentDocumentsPanel view="pending" reloadKey={0} user={agent("master")} />);
    expect(screen.getByText("Loading documents…")).toBeInTheDocument();
    const card = await screen.findByRole("listitem");
    expect(within(card).getByText("Asha Rao")).toBeInTheDocument();
    expect(within(card).getByText("Passport")).toBeInTheDocument();
    expect(within(card).getByText("Pending review")).toBeInTheDocument();
    expect(within(card).getByText("no login")).toBeInTheDocument();
  });

  it("says when a view is empty", async () => {
    stubFetch((url) => (url.includes("/crm/documents?") ? json(page([])) : undefined));
    render(<AgentDocumentsPanel view="pending" reloadKey={0} user={agent("master")} />);
    expect(await screen.findByText("No documents are waiting for review.")).toBeInTheDocument();
  });

  it("offers Retry after a failed load", async () => {
    let calls = 0;
    stubFetch((url) => (url.includes("/crm/documents?") ? (++calls === 1 ? json({ detail: "boom" }, 500) : json(page([DOC]))) : undefined));
    render(<AgentDocumentsPanel view="uploaded" reloadKey={0} user={agent("master")} />);
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Asha Rao")).toBeInTheDocument();
  });

  it("gives a Master three decisions and requires a reason to reject", async () => {
    const fetchMock = stubFetch((url, init) => {
      if (url.includes("/crm/documents?")) return json(page([DOC]));
      if (url.endsWith("/documents/d1/verify") && init?.method === "PATCH") return json({ id: "d1", verification_status: "rejected" });
      return undefined;
    });
    render(<AgentDocumentsPanel view="pending" reloadKey={0} user={agent("master")} />);
    fireEvent.click(await screen.findByRole("button", { name: "Review Passport for Asha Rao" }));
    const decision = screen.getByLabelText("Decision") as HTMLSelectElement;
    expect([...decision.options].map((o) => o.value)).toEqual(["verified", "rejected", "changes_required"]);
    fireEvent.change(decision, { target: { value: "rejected" } });
    const reason = screen.getByLabelText("Reason (required)") as HTMLTextAreaElement;
    expect(reason.required).toBe(true);
    fireEvent.change(reason, { target: { value: "Expired" } });
    fireEvent.click(screen.getByRole("button", { name: "Save decision" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([u, i]) => String(u).endsWith("/verify") && i?.method === "PATCH")).toBe(true));
    const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/verify"))!;
    expect(JSON.parse(String(call[1]!.body))).toEqual({ verification_status: "rejected", notes: "Expired" });
  });

  it("gives staff with Verify one action and staff without none", async () => {
    stubFetch((url) => (url.includes("/crm/documents?") ? json(page([DOC])) : undefined));
    render(<AgentDocumentsPanel view="pending" reloadKey={0} user={agent("staff", true)} />);
    fireEvent.click(await screen.findByRole("button", { name: "Review Passport for Asha Rao" }));
    expect(screen.getByRole("button", { name: "Mark verified" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Decision")).toBeNull();
    cleanup();
    render(<AgentDocumentsPanel view="pending" reloadKey={0} user={agent("staff", false)} />);
    await screen.findByText("Asha Rao");
    expect(screen.queryByRole("button", { name: /^Review/ })).toBeNull();
  });

  it("lists the history in order", async () => {
    stubFetch((url) => {
      if (url.includes("/crm/documents?")) return json(page([DOC]));
      if (url.includes("/documents/d1/history"))
        return json(page([
          { id: "e1", event: "uploaded", actor: "Maya Master", from_status: null, to_status: "pending", notes: null, created_at: "2026-10-02T10:00:00Z" },
          { id: "e2", event: "rejected", actor: "Maya Master", from_status: "pending", to_status: "rejected", notes: "Expired", created_at: "2026-10-02T11:00:00Z" },
        ]));
      return undefined;
    });
    render(<AgentDocumentsPanel view="uploaded" reloadKey={0} user={agent("master")} />);
    fireEvent.click(await screen.findByRole("button", { name: "History of Passport for Asha Rao" }));
    const list = await screen.findByRole("list", { name: "History of Passport for Asha Rao" });
    const items = within(list).getAllByRole("listitem").map((li) => li.textContent);
    expect(items[0]).toContain("Uploaded");
    expect(items[1]).toContain("Rejected");
    expect(items[1]).toContain("Expired");
  });
});

describe("AgentDocumentRequestsPanel", () => {
  it("lists open requests and cancels one", async () => {
    let cancelled = false;
    const request = { id: "r1", agent_student_id: "s1", student: "Asha Rao", document_type: "LOR", document_label: null, note: "Signed", status: "open", requested_by: "Maya", fulfilled_by_document_id: null, created_at: "2026-10-02T10:00:00Z", closed_at: null };
    stubFetch((url, init) => {
      if (url.includes("/document-requests?")) return json(page(cancelled ? [] : [request]));
      if (url.endsWith("/document-requests/r1/cancel") && init?.method === "POST") {
        cancelled = true;
        return json({ request: { ...request, status: "cancelled" } });
      }
      return undefined;
    });
    render(<AgentDocumentRequestsPanel reloadKey={0} />);
    expect(await screen.findByText("Signed")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cancel request for LOR from Asha Rao" }));
    expect(await screen.findByText("No open requests. Requests you make appear here until a document is uploaded against them.")).toBeInTheDocument();
  });
});

describe("AgentDocumentUploadForm", () => {
  it("asks for a description only when the type is Other", () => {
    stubFetch(() => undefined);
    render(<AgentDocumentUploadForm onUploaded={() => {}} />);
    expect(screen.queryByLabelText("Description")).toBeNull();
    fireEvent.change(screen.getByLabelText("Document type"), { target: { value: "Other" } });
    expect((screen.getByLabelText("Description") as HTMLInputElement).required).toBe(true);
    expect((screen.getByLabelText("File (PDF, JPEG or PNG)") as HTMLInputElement).accept).toContain("application/pdf");
  });
});

describe("AgentDocumentRequestForm", () => {
  it("offers the fixed document types", () => {
    stubFetch(() => undefined);
    render(<AgentDocumentRequestForm onCreated={() => {}} />);
    const options = [...(screen.getByLabelText("Document type") as HTMLSelectElement).options].map((o) => o.value);
    expect(options).toEqual(["Passport", "Academic certificates", "Transcripts", "English test", "CV", "SOP", "LOR", "Financial documents", "Other"]);
  });
});
